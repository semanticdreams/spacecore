from pathlib import Path
import re
import shlex

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


class WorkflowLoader(yaml.SafeLoader):
    pass


for first_char, mappings in list(WorkflowLoader.yaml_implicit_resolvers.items()):
    WorkflowLoader.yaml_implicit_resolvers[first_char] = [
        (tag, regexp)
        for tag, regexp in mappings
        if tag != "tag:yaml.org,2002:bool"
    ]


def read_repo_text(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def load_workflow(relative_path: str) -> dict:
    return yaml.load(read_repo_text(relative_path), Loader=WorkflowLoader)


def find_step(job: dict, field: str, value: str) -> dict:
    matches = [step for step in job["steps"] if step.get(field) == value]
    assert len(matches) == 1, (field, value, matches)
    return matches[0]


def test_main_push_manual_windows_validation_keeps_native_fast_and_no_installer() -> None:
    # 2f94237a deliberately moved Windows out of PR/merge-queue gating;
    # ae16caee added the corresponding routing guard and policy documentation.
    workflow = load_workflow(".github/workflows/windows.yml")
    jobs = workflow["jobs"]
    gate = load_workflow(".github/workflows/test.yml")

    assert set(workflow["on"]) == {"push", "workflow_dispatch"}
    assert workflow["on"]["push"] == {"branches": ["main"]}
    assert {"pull_request", "merge_group"} <= set(gate["on"])
    assert gate["jobs"]["test"]["runs-on"] == "ubuntu-22.04"
    assert not {"build-windows", "test-windows", "build-windows-installer"} & set(gate["jobs"])
    assert "build-windows" in jobs
    assert "test-windows" in jobs
    assert "build-windows-installer" not in jobs
    assert jobs["build-windows"]["runs-on"] == "ubuntu-24.04"
    assert jobs["test-windows"]["needs"] == "build-windows"
    assert jobs["test-windows"]["runs-on"] == "windows-latest"
    fast = find_step(jobs["test-windows"], "name", "Run Windows fast suite")
    assert shlex.split(fast["run"], posix=False) == [r".\build\dist\windows\space-cli.exe", "-m", "tests.fast:main"]
    assert fast["env"]["SPACE_BIN"] == r"${{ github.workspace }}\\build\\dist\\windows\\space-cli.exe"
    assert fast["env"]["SPACE_ASSETS_PATH"] == r"${{ github.workspace }}\\build\\dist\\windows\\assets"


def test_windows_validation_uploads_runtime_only_and_no_packaging_inputs() -> None:
    workflow = load_workflow(".github/workflows/windows.yml")
    text = read_repo_text(".github/workflows/windows.yml")
    build = workflow["jobs"]["build-windows"]
    upload = find_step(build, "uses", "actions/upload-artifact@v5")
    download = find_step(workflow["jobs"]["test-windows"], "uses", "actions/download-artifact@v5")

    assert shlex.split(find_step(build, "name", "Build Windows target")["run"]) == ["scripts/build-windows-from-linux.sh"]
    assert shlex.split(find_step(build, "name", "Prepare runtime bundle")["run"]) == ["scripts/package-windows-runtime.sh"]
    assert upload["with"] == {"name": "space-windows-runtime", "path": "build/dist/windows", "if-no-files-found": "error"}
    assert download["with"] == {"name": "space-windows-runtime", "path": "build/dist/windows"}
    assert "windows-packaging-inputs" not in text
    assert "Create Windows ZIP" not in text
    assert "Verify Windows ZIP contents" not in text
    assert "space-windows-x86_64.zip" not in text
    assert "space-windows-x86_64-setup.exe" not in text
    assert "scripts/build-windows-installer.py" not in text
    assert "choco install innosetup" not in text


def test_release_workflow_keeps_windows_zip_and_installer_packaging_paths() -> None:
    workflow = load_workflow(".github/workflows/build.yml")
    jobs = workflow["jobs"]
    text = read_repo_text(".github/workflows/build.yml")

    assert "build-windows" in jobs
    assert "build-windows-installer" in jobs
    assert jobs["build-windows"]["runs-on"] == "ubuntu-24.04"
    assert jobs["build-windows-installer"]["needs"] == "build-windows"
    assert set(workflow["on"]) == {"push", "workflow_dispatch"}
    assert workflow["on"]["push"] == {"tags": ["v*"]}
    assert "space-windows-x86_64.zip" in text
    assert "space-windows-x86_64-setup.exe" in text
    installer = jobs["build-windows-installer"]
    assert installer["runs-on"] == "windows-latest"
    install = find_step(installer, "name", "Install Inno Setup")
    assert install["shell"] == "pwsh"
    tokens = shlex.split(install["run"])
    assert tokens[:3] == ["choco", "install", "innosetup"]
    flags = tokens[3:]
    assert flags.count("--version") == 1
    version_index = flags.index("--version")
    assert flags[version_index + 1] == "$env:INNOSETUP_CHOCO_VERSION"
    assert workflow["env"]["INNOSETUP_CHOCO_VERSION"] == "6.4.3"
    del flags[version_index:version_index + 2]
    assert sorted(flags) == ["--no-progress", "-y"]
    build_installer = find_step(installer, "name", "Build Windows installer")
    assert build_installer["shell"] == "pwsh"
    assert shlex.split(build_installer["run"]) == ["python", "scripts/build-windows-installer.py"]
    assert find_step(installer, "uses", "actions/download-artifact@v5")["with"]["name"] == "windows-packaging-inputs"
    release = find_step(jobs["publish-release"], "uses", "softprops/action-gh-release@v2")
    assert release["with"]["files"] == "build/release-artifacts/**"


def test_windows_cross_build_jobs_enable_ninja_sccache_binary_and_vcpkg_cache() -> None:
    action_path = ".github/actions/setup-windows-cross-cache"
    action = load_workflow(f"{action_path}/action.yml")
    assert action["runs"]["using"] == "composite"
    assert action["inputs"]["sccache-version"]["default"] == "0.16.0"
    assert action["inputs"]["export-vcpkg-cache-runtime"]["default"] == "false"
    composite = action["runs"]
    for cache, directory in [("ccache", "ccache-path"), ("sccache", "sccache-path")]:
        restore = find_step(composite, "name", f"Restore {cache}")
        assert restore["uses"] == "actions/cache@v5"
        assert restore["with"]["path"] == "${{ inputs." + directory + " }}"
        prefix = cache + "-${{ runner.os }}-${{ inputs.cache-scope }}-"
        key_files = cache + "-key-files"
        assert restore["with"]["key"] == prefix + "${{ github.ref }}-${{ hashFiles(inputs." + key_files + ") }}"
        assert restore["with"]["restore-keys"].splitlines() == [prefix + "${{ github.ref }}-", prefix]
    binary = find_step(composite, "name", "Restore sccache binary")
    assert binary["uses"] == "actions/cache@v5"
    assert binary["with"] == {"path": "~/.cargo/bin/sccache", "key": "sccache-bin-${{ runner.os }}-${{ inputs.sccache-version }}"}
    install = find_step(composite, "name", "Install sccache")
    assert install["shell"] == "bash"
    cargo_lines = [line for line in install["run"].splitlines() if line.strip().startswith("cargo install ")]
    assert len(cargo_lines) == 1
    assert shlex.split(cargo_lines[0]) == ["cargo", "install", "sccache", "--version", "${{ inputs.sccache-version }}", "--locked"]
    export = find_step(composite, "name", "Export GitHub Actions cache runtime for vcpkg")
    assert export["if"] == "inputs.export-vcpkg-cache-runtime == 'true'"
    assert export["uses"] == "actions/github-script@v8"
    variables = re.findall(r"core\.exportVariable\('([^']+)',\s*process\.env\.([A-Z_]+)\s*\|\|\s*''\);", export["with"]["script"])
    assert variables == [(name, name) for name in ("ACTIONS_CACHE_URL", "ACTIONS_RESULTS_URL", "ACTIONS_RUNTIME_TOKEN")]

    for workflow_path in [".github/workflows/windows.yml", ".github/workflows/build.yml"]:
        workflow = load_workflow(workflow_path)
        job = workflow["jobs"]["build-windows"]
        env = job["env"]

        assert job["permissions"]["contents"] == "read"
        assert job["permissions"]["actions"] == "write"
        assert env["CMAKE_GENERATOR"] == "Ninja"
        assert env["VCPKG_FEATURE_FLAGS"] == "binarycaching"
        assert "VCPKG_BINARY_SOURCES" in env
        setup = find_step(job, "uses", f"./{action_path}")
        inputs = setup["with"]
        assert inputs["cache-scope"] == "windows-cross"
        assert inputs["ccache-path"] == ".ccache-windows"
        assert inputs["sccache-path"] == ".sccache-windows"
        assert env["CCACHE_DIR"] == "${{ github.workspace }}/" + inputs["ccache-path"]
        assert env["SCCACHE_DIR"] == "${{ github.workspace }}/" + inputs["sccache-path"]
        assert "sccache-version" not in inputs  # Both callers consume the checked exact default.
        assert str(inputs["export-vcpkg-cache-runtime"]).lower() == "true"
        for key in ("ccache-key-files", "sccache-key-files"):
            assert {"CMakeLists.txt" if key == "sccache-key-files" else "**/CMakeLists.txt",
                    "scripts/build-windows.sh", "scripts/build-windows-from-linux.sh",
                    "scripts/setup-windows-build-host.sh"} <= set(inputs[key].splitlines())
        if workflow_path.endswith("build.yml"):
            assert {"scripts/build-windows-installer.py", "scripts/windows-installer.iss"} <= set(inputs["ccache-key-files"].splitlines())
        build = next(step for step in job["steps"] if shlex.split(step.get("run", "")) == ["scripts/build-windows-from-linux.sh"])
        assert build["env"]["CMAKE_C_COMPILER_LAUNCHER"] == "ccache"
        assert build["env"]["CMAKE_CXX_COMPILER_LAUNCHER"] == "ccache"


def test_windows_vcpkg_cache_keeps_pr_read_only_defense_and_manual_writes() -> None:
    workflow = load_workflow(".github/workflows/windows.yml")
    source = workflow["jobs"]["build-windows"]["env"]["VCPKG_BINARY_SOURCES"]

    # Match the actual conditional, not a 'read' substring inside 'readwrite'.
    branches = re.fullmatch(r"\$\{\{\s*github\.event_name\s*==\s*'pull_request'\s*&&\s*'([^']+)'\s*\|\|\s*'([^']+)'\s*\}\}", source)
    assert branches is not None
    assert branches.groups() == ("clear;x-gha,read", "clear;x-gha,readwrite")
    assert set(workflow["on"]) == {"push", "workflow_dispatch"}  # PR mode is defensive, not a trigger.
    for event, expected in [("pull_request", "clear;x-gha,read"), ("push", "clear;x-gha,readwrite"),
                            ("workflow_dispatch", "clear;x-gha,readwrite")]:
        assert branches[1 if event == "pull_request" else 2] == expected
    release = load_workflow(".github/workflows/build.yml")
    assert set(release["on"]) == {"push", "workflow_dispatch"}
    assert release["jobs"]["build-windows"]["env"]["VCPKG_BINARY_SOURCES"] == "clear;x-gha,readwrite"


def test_build_windows_script_builds_targets_in_parallel() -> None:
    script = read_repo_text("scripts/build-windows.sh")

    assert "resolve_build_jobs()" in script
    assert 'BUILD_JOBS="$(resolve_build_jobs)"' in script
    assert "BUILD_JOBS must be a positive integer" in script
    assert 'cmake --build "${BUILD_DIR}" --config Release --parallel "${BUILD_JOBS}" --target space space-cli' in script


def test_build_windows_script_resets_stale_cache_when_generator_changes() -> None:
    script = read_repo_text("scripts/build-windows.sh")

    assert 'CMAKE_GENERATOR:INTERNAL=${CMAKE_GENERATOR}' in script
    assert 'Resetting ${BUILD_DIR} due to stale CMake cache.' in script


def test_windows_wine_notes_document_validation_packaging_boundary_and_speedups() -> None:
    text = read_repo_text("docs/dev/notes/windows-wine-build-and-test.md")

    assert "`test.yml` Linux PR/merge-queue validation path" in text
    assert "`windows.yml` Windows main-push/manual validation path" in text
    assert "Windows validation is post-merge, not a PR or merge-queue gate" in text
    assert "does not build the Windows installer" in text
    assert "does not create the release ZIP" in text
    assert "Release/manual packaging path" in text
    assert "existing `workflow_dispatch` behavior remains available" in text
    assert "vcpkg binary caching" in text
    assert "Ninja parallel builds" in text
