"""Deterministic derived projection and post-commit failure contracts."""

import pytest

from helpers_requirements import (
    apply_request, create_op, init_ok, read_ledger_bytes, requirements_lib,
    run_cli,
)


def test_render_deterministic_check_only_and_staleness(tmp_path):
    init_ok(tmp_path)
    index = tmp_path / "docs/requirements/index.md"
    before = read_ledger_bytes(tmp_path)
    check = run_cli(tmp_path, "render", "--check")
    assert check.returncode == 1
    assert check.error_code() == "projection-stale"
    assert not index.exists()
    assert read_ledger_bytes(tmp_path) == before
    assert run_cli(tmp_path, "render").returncode == 0
    first = index.read_bytes()
    assert run_cli(tmp_path, "render").returncode == 0
    assert index.read_bytes() == first
    assert run_cli(tmp_path, "render", "--check").returncode == 0
    index.write_text("stale")
    assert run_cli(tmp_path, "render", "--check").error_code() == "projection-stale"
    assert index.read_text() == "stale"


def test_apply_refreshes_projection_and_escapes_markdown(tmp_path):
    init_ok(tmp_path)
    result = run_cli(tmp_path, "apply", request=apply_request(create_op(statement="A | B\n<script>")))
    assert result.returncode == 0, result.stdout + result.stderr
    index = tmp_path / "docs/requirements/index.md"
    assert index.exists()
    assert "A &#124; B<br>&lt;script&gt;" in index.read_text()
    assert "Revision: 1" in index.read_text()
    assert run_cli(tmp_path, "render", "--check").returncode == 0


def test_projection_failure_reports_committed_revision_not_rollback(tmp_path, monkeypatch):
    init_ok(tmp_path)
    lib = requirements_lib()
    import importlib
    render = importlib.import_module(lib.__name__ + ".render")
    def fail(*args, **kwargs):
        raise OSError("projection disk unavailable")
    monkeypatch.setattr(render, "write_projection", fail)
    with pytest.raises(lib.RequirementsError) as error:
        lib.apply(tmp_path, apply_request(create_op(), expected_revision=0))
    assert error.value.code == "projection-stale"
    assert error.value.envelope()["revision"] == 1
    assert error.value.details["committed_revision"] == 1
    assert error.value.details["projection_stale"] is True
    assert lib.load_ledger(tmp_path)["revision"] == 1


def test_render_missing_ledger_never_initializes(tmp_path):
    result = run_cli(tmp_path, "render", "--check")
    assert result.returncode == 1
    assert result.error_code() == "ledger-missing"
    assert list(tmp_path.iterdir()) == []


def test_projection_cli_failure_is_nonzero_and_canonical_commit_survives(tmp_path):
    init_ok(tmp_path)
    (tmp_path / "docs/requirements/index.md").mkdir()
    result = run_cli(tmp_path, "apply", request=apply_request(create_op()))
    assert result.returncode == 1
    assert result.error_code() == "projection-stale"
    assert result.json["revision"] == 1
    assert result.json["error"]["details"]["projection_stale"] is True
    assert requirements_lib().load_ledger(tmp_path)["revision"] == 1
    assert not result.stderr


def test_projection_outside_root_symlink_is_not_read_or_written(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    init_ok(repo)
    outside = tmp_path / "outside.md"
    outside.write_text("private outside content")
    index = repo / "docs/requirements/index.md"
    index.symlink_to(outside)
    check = run_cli(repo, "render", "--check")
    assert check.returncode == 1
    assert check.error_code() == "invalid-locator"
    result = run_cli(repo, "apply", request=apply_request(create_op()))
    assert result.returncode == 1
    assert result.error_code() == "projection-stale"
    assert result.json["revision"] == 1
    assert outside.read_text() == "private outside content"
    assert index.is_symlink()


def test_stale_write_does_not_claim_a_committed_request_revision(tmp_path):
    init_ok(tmp_path)
    assert run_cli(tmp_path, "apply", request=apply_request(create_op())).returncode == 0
    result = run_cli(tmp_path, "apply", request=apply_request(create_op(), expected_revision=0))
    assert result.returncode == 1
    assert result.error_code() == "expected-revision-stale"
    assert result.json["revision"] is None
    assert result.json["error"]["details"]["committed_revision"] == 1


@pytest.mark.parametrize("verb", ["apply", "render"])
@pytest.mark.parametrize("alias", ["direct", "dot", "absolute", "ledger-symlink", "parent-symlink", "projection-symlink"])
def test_custom_ledger_projection_collision_preserves_canonical_bytes(tmp_path, verb, alias):
    projection = tmp_path / "docs/requirements/index.md"
    canonical = "docs/requirements/custom.json" if alias == "projection-symlink" else "docs/requirements/index.md"
    initialized = run_cli(tmp_path, "init", "--ledger", canonical)
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    path = tmp_path / canonical
    before = path.read_bytes()
    selected = canonical
    if alias == "dot":
        selected = "docs/requirements/./index.md"
    elif alias == "absolute":
        selected = str(projection)
    elif alias == "ledger-symlink":
        link = projection.with_name("alias.json")
        link.symlink_to(projection.name)
        selected = "docs/requirements/alias.json"
    elif alias == "parent-symlink":
        (tmp_path / "docs/alias").symlink_to("requirements", target_is_directory=True)
        selected = "docs/alias/index.md"
    elif alias == "projection-symlink":
        projection.symlink_to(path.name)
    request = apply_request(create_op(), expected_revision=0) if verb == "apply" else None
    result = run_cli(tmp_path, verb, "--ledger", selected, request=request)
    assert result.returncode == 1
    assert result.error_code() == "ledger-projection-collision"
    assert result.json["revision"] is None
    assert not result.stderr
    assert path.read_bytes() == before
    assert requirements_lib().load_ledger(tmp_path, selected)["revision"] == 0


def test_lone_surrogate_postcommit_projection_failure_is_honest(tmp_path):
    init_ok(tmp_path)
    assert run_cli(tmp_path, "render").returncode == 0
    index = tmp_path / "docs/requirements/index.md"
    projection_before = index.read_bytes()
    canonical_before = read_ledger_bytes(tmp_path)
    statement = "Escaped lone surrogate: \ud800"
    result = run_cli(tmp_path, "apply", request=apply_request(create_op(statement=statement)))
    assert result.returncode == 1
    assert result.error_code() == "projection-stale"
    assert result.json["revision"] == 1
    assert result.json["error"]["details"]["committed_revision"] == 1
    assert result.json["error"]["details"]["projection_stale"] is True
    assert not result.stderr
    committed = read_ledger_bytes(tmp_path)
    assert committed != canonical_before and b"\\ud800" in committed
    ledger = requirements_lib().load_ledger(tmp_path)
    assert ledger["revision"] == 1
    assert next(iter(ledger["requirements"].values()))["statement"] == statement
    assert index.read_bytes() == projection_before
    for flags in ((), ("--check",)):
        retry = run_cli(tmp_path, "render", *flags)
        assert retry.returncode == 1
        assert retry.error_code() == "projection-stale"
        assert retry.json["revision"] == 1
        assert not retry.stderr
        assert read_ledger_bytes(tmp_path) == committed
        assert index.read_bytes() == projection_before
    assert not list(index.parent.glob(".index.md.*.tmp"))
