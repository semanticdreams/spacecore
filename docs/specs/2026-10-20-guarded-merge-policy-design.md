# Guarded merge-queue policy verification

## Problem and evidence

Daily devlog run 82 successfully dispatched after the Orca setup-binding repair, but stopped before edits because the guarded GitHub helper could not prove the workflow's PR requirement or supported merge method. Authentication, required `test`, and merge queue were proven. These observations establish missing helper evidence, not disabled GitHub settings.

`scripts/opencode_pr_operator.py:215-270` currently reports only check/queue proofs using potentially incomplete ruleset summaries/details. `enable_auto_merge` at lines 322-341 hardcodes `--merge`. GitHub's queue controls the final method and ignores client strategy selection. The user approved repairing this mismatch; historical devlog backfill and GitHub setting changes are not part of this change.

## Direction and alternatives

Require complete effective branch rules, repository merge permissions, and explicit queue-method proof inside the existing capability. This is preferable to extending the bounded ruleset-detail fallback into a local applicability engine. Merely adding PR-presence output while retaining the hardcoded strategy would leave the safety contract incomplete.

Keep wrapper commands, public operation signatures, result envelopes, and capability permissions unchanged. Production changes belong in the Python PR operator; tests belong in its existing pytest module. Update the existing canonical capability and devlog notes, without introducing new runtime systems.

## Proof contract

- Fetch all pages of `repos/semanticdreams/spacecore/rules/branches/main` using `gh api --paginate --slurp` with `per_page=100`. Validate all page/rule shapes before evaluation; failed or partial retrieval cannot authorize mutation. Do not locally reconstruct inheritance or applicability.
- Read repository metadata and classic branch protection. A readable classic object can supply exact `test` and configured `required_pull_request_reviews` proof even with zero approvals. An explicit HTTP 404 may be recorded as unavailable if complete effective rules independently supply both proofs. Other classic errors, malformed data, and unreadable mandatory evidence fail closed.
- Require exact required check `test`, required PR, and effective merge queue. Every queue rule must expose a recognized, consistent `MERGE`, `SQUASH`, or `REBASE` method. Only merge or squash can pass; rebase-only requires a human decision.
- The queue method's repository permission must literally be boolean true. Every explicit PR `allowed_merge_methods` list must be well-formed and permit that method; intersect restrictions across all pages. Missing optional lists supply no additional explicit restriction, not affirmative permission for every method: the explicit queue configuration and repository permission remain mandatory. Explicit malformed/null/empty restrictions cannot grant permission.
- Merge commits conflict with effective or readable classic linear-history requirements. Squash can satisfy linear history. Malformed relevant policy must produce a diagnostic refusal, not disappear.
- Emit repository identity, effective-rules completeness/page count, source and aggregate PR/check/queue proofs, repository permission facts, explicit restrictions, queue method, safe-method proof, and actionable blockers. Retire obsolete summary/detail authorization evidence rather than fabricate compatibility facts.

## Mutation and error behavior

Immediately before requesting auto-merge, rerun the strengthened proof. For a proven merge-queue policy invoke `gh pr merge <safe-branch> --auto` with no strategy or administrative bypass flags. Report the verified queue method, not a client-selected strategy or a claim of actual merge. Preserve structured command-failure evidence and do not retry alternate methods. Existing merge-queue polling still requires `mergedAt`.

No changes to GitHub configuration, agent permissions, PR recovery, branch safety, queue polling, or unrelated engine/Fennel code. GitHub remains authoritative for concurrent policy changes and server-side enforcement.

## Validation and acceptance

Regression tests must first expose missing PR/method proofs and the hardcoded strategy, then cover full pagination (including later-page restrictions), classic zero approvals/404/errors, safe merge/squash, absent optional PR lists, missing or malformed permissions/policy, rebase/conflicting queue methods, linear history, and refusal-before-mutation. Existing unrelated PR/recovery behavior must remain green.

Run focused pytest, the PR/recovery tests, `make opencode-check`, diff whitespace review, and docs build after documentation changes. No native build or Fennel checks are warranted. Through `github-operator`, rerun the existing read-only `check-main-protection` wrapper and inspect actual evidence. Fetch current `origin/main` before final validation/integration. Land reviewed changes through a PR and poll to actual merge; then retry automation from the landed helper. A genuine access or incompatible-policy blocker must be reported without weakening guards.

## Public API references

- https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch
- https://docs.github.com/en/rest/repos/repos#get-a-repository
- https://docs.github.com/en/rest/branches/branch-protection
- https://cli.github.com/manual/gh_pr_merge
- https://docs.github.com/en/graphql/reference/pulls#enablepullrequestautomergeinput

Self-review: scope is bounded to existing capability proof and queue request behavior; optional-field and classic-404 boundaries are explicit; no unresolved design choice requires a human checkpoint.
