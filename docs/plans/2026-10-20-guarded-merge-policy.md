# Guarded Merge Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore guarded automation by proving PR protection and a safe queue method before requesting auto-merge.

**Architecture:** Replace incomplete summary/detail authorization with fully paginated effective branch rules and repository metadata, supplemented by bounded classic protection. Evaluate every applicable explicit restriction and request queue auto-merge without a client strategy. Keep code, fixtures and docs together in one coherent review unit.

**Tech Stack:** Python standard library, pytest, GitHub CLI/REST API, VitePress.

## Global Constraints

- "Keep wrapper commands, public operation signatures, result envelopes, and capability permissions unchanged."
- "Do not locally reconstruct inheritance or applicability."
- "Only merge or squash can pass; rebase-only requires a human decision."
- "Explicit malformed/null/empty restrictions cannot grant permission."
- "Preserve structured command-failure evidence and do not retry alternate methods."
- "Existing merge-queue polling still requires `mergedAt`."
- "No changes to GitHub configuration, agent permissions, PR recovery, branch safety, queue polling, or unrelated engine/Fennel code."
- Specification: `docs/specs/2026-10-20-guarded-merge-policy-design.md`.

---

### Task 1: Prove Safe Queue Policy and Repair the Request Boundary

**Files:**
- Modify `scripts/opencode_pr_operator.py`: retrieval, proof evaluation, strategy-free request.
- Modify `scripts/tests/test_opencode_pr_operator.py`: migrate fixtures and add regressions.
- Modify `docs/dev/features/opencode-agent-workflow.md`: canonical guarded policy contract.
- Modify `docs/dev/notes/daily-devlog-automation.md`: correct strategy-selection explanation.
- Validate unchanged `scripts/tests/test_opencode_pr_recovery.py` and capability gate.

**Interfaces:** Preserve `check_main_protection(repo_root: Path) -> dict[str, object]`, `enable_auto_merge(repo_root: Path, branch: str) -> dict[str, object]`, and current-branch wrappers. Add small private retrieval/evaluation helpers within the existing file. Consume existing `run_command`, `CapabilityError`, result constructors and repository validator. Do not add modules, dependencies, CLI arguments or permission rules.

- [ ] **Step 1: Establish baseline and RED.** Run `python3 -m pytest scripts/tests/test_opencode_pr_operator.py scripts/tests/test_opencode_pr_recovery.py -q`. Add focused tests exposing old false-positive missing-PR/rebase-queue acceptance and the hardcoded strategy. Example mutation-boundary test:

```python
@pytest.mark.parametrize("method", ["merge", "squash"])
def test_queue_request_has_no_strategy(monkeypatch, trusted_repo, method):
    proof = {"status": "pass", "evidence": {
        "queue_merge_method": method, "safe_merge_method_proven": True}}
    monkeypatch.setattr(pr_operator, "check_main_protection", lambda _: proof)
    command = ["gh", "pr", "merge", "feature/opencode-capabilities", "--auto"]
    runner = GhRunner({tuple(command): ""})
    monkeypatch.setattr(pr_operator, "run_command", runner)
    result = pr_operator.enable_auto_merge(trusted_repo, "feature/opencode-capabilities")
    assert result["status"] == "pass"
    assert runner.calls == [command]
    assert result["evidence"]["queue_merge_method"] == method
```

Record meaningful failing assertions before production changes. Make `GhRunner` reject unexpected commands so missing mocks cannot silently pass.

- [ ] **Step 2: Retrieve complete evidence.** Use this fixed effective endpoint command and validate successful slurped page arrays, nonempty outer pages, every inner array and object rule with nonempty string `type`:

```python
args = ["gh", "api", "--paginate", "--slurp",
        f"repos/{SPACE_REPO}/rules/branches/main?per_page=100"]
result = run_command(args, repo, check=False)
# A nonzero status refuses even if stdout contains partial valid JSON.
pages = json.loads(result.stdout)
# Validate before flattening; [[]] is complete but proves no protection.
rules = [rule for page in pages for rule in page]
```

Read `gh api repos/{SPACE_REPO}` and `gh api repos/{SPACE_REPO}/branches/main/protection`. Require object metadata. Classic successful object supplies supplemental proofs; explicit `HTTP 404` diagnostic is allowed only with independent effective PR/test proof. Do not infer 404 from process status or generic text. Other classic errors/malformed data refuse. Retain command arguments, return code and stderr in errors. Remove obsolete ruleset-summary/detail requests, matchers and constants rather than retain incomplete policy authorization.

- [ ] **Step 3: Evaluate all relevant rules.** Require exact `test`, PR presence, queue presence and one consistent uppercase queue method. A classic review-protection object, including zero approvals or `{}`, proves PR presence. Missing/null classic fields do not. Validate present check collections and relevant policy types. Queue parameters/method are mandatory. PR parameters are optional but must be objects if present; optional absent method lists add no explicit restriction. Present lists must contain only lowercase `merge`, `squash`, `rebase`; null/scalar/unknown values refuse and empty lists allow nothing. Ignore unrelated well-formed rule types. Use literal permission and intersection logic:

```python
permission_keys = {"merge": "allow_merge_commit", "squash": "allow_squash_merge"}
method = queue_methods[0].lower()  # only after recognized, consistent methods proved
safe = method in permission_keys
safe = safe and metadata.get(permission_keys[method]) is True
safe = safe and all(method in allowed for allowed in explicit_pr_restrictions)
safe = safe and not (method == "merge" and linear_history_required)
```

Never index the safe-only mapping for rebase. Effective linear-history presence or readable classic `required_linear_history.enabled == True` excludes merge; malformed present classic configuration refuses. Accumulate blockers even after finding positive proofs. Report repository identity, source/aggregate PR/test/queue proofs, completeness/page count, metadata and classic status, repository permissions, restrictions, queue method, linear history, safe method and actionable blockers. Retire obsolete summary/detail evidence fields.

- [ ] **Step 4: Repair mutation boundary.** Recheck policy immediately before mutation. Refuse any non-pass result. Use `run_command(["gh", "pr", "merge", safe, "--auto"], repo, check=False)` with no strategy/admin flags. Include verified queue method and proof in result. On failure preserve stderr/status/arguments and do not retry. Remove the post-mutation `rebase` substring heuristic. Success means request accepted, not actual merge. Preserve unrelated public behavior.

- [ ] **Step 5: Complete regression matrix and GREEN.** Cover safe merge/squash, optional absent lists, classic zero approvals/empty object/404/401/403/malformed/error, missing PR/test/queue, full pagination and later-page proof/restriction/conflict, partial failed pagination, malformed JSON/pages/rules, empty effective results, missing/unreadable metadata, literal-vs-truthy permissions, missing/unknown/rebase/conflicting queue methods, intersected restrictions, null/scalar/empty restrictions, linear-history merge refusal/squash success, malformed relevant policy despite other valid proof, unrelated rule types, command failures, current-branch and unsafe-branch behavior. Every refusal exercised through auto-merge must assert no `gh pr merge` mutation. Migrate existing successful fixtures to full evidence; replace old detail-fallback success with mandatory-effective-evidence refusal. Run focused tests then full PR/recovery modules.

- [ ] **Step 6: Update owning docs.** In the existing strict capability page explain complete effective rules, repo permissions, exact PR/test/queue proofs, optional-list and classic-404 boundaries, safe queue methods, restrictions, linear history and diagnostics. Replace devlog note's client strategy-selection sentence with queue-authoritative, strategy-free behavior and link to canonical subsection. Do not add new feature pages or alter scheduler/attribution guidance.

- [ ] **Step 7: Validate and independently review.** Run `python3 -m pytest scripts/tests/test_opencode_pr_operator.py scripts/tests/test_opencode_pr_recovery.py -q`, `make opencode-check`, `git diff --check`, and docs `npm run docs:build` after `npm ci` if locked dependencies are missing. Inspect generated diffs; no unrelated generated changes. Through `github-operator` run existing read-only `check-main-protection --repo-root .` and inspect live proof. No raw `gh` or auto-merge smoke mutation. Review all four files and RED/GREEN evidence against spec; fix through implementer/reviewer until pass. Native/Fennel/full engine tests are not applicable to this Python/docs surface.

- [ ] **Step 8: Commit and integrate after review.** Stage only reviewed task files; commit with `fix(scripts): prove safe merge queue policy before auto-merge`. Follow current `origin/main` fetch/safe-merge/clean-tree requirements, rerun required validation on updated base, push through `git-integrator`, and create/queue PR through `github-operator`. Poll until `mergedAt`, not queue handoff. Diagnose required failures; no rebase/force push/bypass. After landing retry automation safeguards using landed helper, preserving historical backfill as separate work.

Self-review: every spec requirement maps to this coherent task; proof, retrieval, optional-field boundaries, mutation behavior, tests, docs and integration are explicit. No unresolved design ambiguity or placeholder implementation step remains.
