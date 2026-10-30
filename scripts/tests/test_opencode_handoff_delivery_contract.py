"""Source-contract guards, not a runtime report parser or model-compliance proof.

The unchanged Task 5 fixtures cover transitions/replay; these guards cover the
instructions that the three receiving controllers and original authors load.
"""
import json
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]
AUTHORS = ("implementer", "planner", "reviewer", "debug-advisor", "adjudicator", "fast-dev-reviewer")


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def section(path, heading):
    body = text(path).split(heading + "\n", 1)
    assert len(body) == 2, f"{path}: missing {heading}"
    level = len(heading.split(" ", 1)[0])
    return " ".join(re.split(rf"\n#{{1,{level}}} ", body[1], maxsplit=1)[0].split())


@pytest.mark.parametrize("terms", [
    ("task", "original author", "selected controller", "branch", "source snapshot", "base/head", "review mode"),
    ("correction_used=0/1", "separate from the identity", "not an attempt in the key", "before dispatch"),
    ("declared role format", "required fields", "identity", "range", "before consultation, verdict, fix, cap or completion"),
    ("Valid initial and corrected deliveries", "ELIGIBLE_FOR_NORMAL_HANDLING", "semantic", "not approval", "framing"),
    ("original author", "retained author records", "precise delivery errors", "original and corrected payloads separately"),
    ("No caller-side fence stripping", "aliases", "defaults", "partial verdict salvage"),
    ("No verdict, findings, evidence or range facts", "unambiguous assignment metadata"),
    ("format-only is an assignment mode", "not an extra JSON response key", "no universal new status or field"),
    ("existing context/evidence-needed or non-approving branch", "NEEDS_CONTEXT only where supported"),
    ("missing/changed/stale/untrusted scope", "author unavailable", "new worker", "paper SHAs"),
    ("one invalid correction", "no second", "rename", "redispatch", "Duplicates do not reset"),
    ("new authorized substantive scope/range", "actual new work", "normal review flow", "not an automatic fresh-review loophole"),
    ("Expert-submitted answers", "capability wrapper JSON/refusals", "rerun privileged operations"),
    ("neither consumes nor resets", "code-fix", "consultation budgets", "before dependent implementation"),
    ("direct edits/fixes", "local checkpoints", "explicit wrap-up", "one observational review", "no app manual setup or refresh"),
])
def test_canonical_delivery_invariants(terms):
    rule = section("AGENTS.md", "### Fail-closed handoff delivery")
    for term in terms:
        assert term in rule, f"canonical delivery rule missing {term!r}"


@pytest.mark.parametrize("name", ("supervisor", "fast-dev", "live-dev"))
def test_parent_gate_precedes_semantic_handlers(name):
    path = f".opencode/agents/{name}.md"
    hook = section(path, "## Handoff delivery gate (before all report handling)")
    for term in ("AGENTS.md#fail-closed-handoff-delivery", "declared role format", "required fields",
                 "identity", "range", "before consultation, verdict, fix, cap or completion handling",
                 "correction_used", "before dispatch", "same original author", "normal semantic handling", "not approval"):
        assert term in hook
    body = text(path)
    handler = "## Consultation routing" if name == "supervisor" else "## Consultation and direct development"
    assert body.index("## Handoff delivery gate") < body.index(handler)


@pytest.mark.parametrize("name", AUTHORS)
def test_author_format_only_assignment_overrides_operational_obligations(name):
    hook = section(f".opencode/agents/{name}.md", "## Format-only redelivery assignment")
    for term in ("AGENTS.md#fail-closed-handoff-delivery", "retained author records", "declared response format",
                 "no code edits, tests, builds, commits or operations", "ordinary task obligations",
                 "unchanged", "not an extra response key", "existing", "non-approving"):
        assert term in hook
    assert "NEEDS_CONTEXT" not in hook or name in ("implementer", "planner")


@pytest.mark.parametrize("name", ("subagent-driven-development", "systematic-debugging", "fast-dev-wrap-up"))
def test_skill_receivers_reference_gate_before_existing_transitions(name):
    hook = section(f".opencode/skills/{name}/SKILL.md", "## Handoff delivery preflight")
    for term in ("AGENTS.md#fail-closed-handoff-delivery", "before consultation, verdict, fix, cap or completion",
                 "same-author format-only", "not a code-fix round", "not approval"):
        assert term in hook


@pytest.mark.parametrize("name,required", [
    ("planner", "Otherwise return only raw Markdown suitable for PLAN.md"),
    ("implementer", "**Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT"),
    ("reviewer", "Return only one valid JSON object, with no Markdown fence"),
    ("debug-advisor", "Return only a single JSON object, no Markdown fence"),
    ("adjudicator", "Return only one valid JSON object, with no Markdown fence"),
    ("fast-dev-reviewer", "For this pending branch return only raw JSON, without a Markdown fence"),
])
def test_role_formats_remain_role_specific_without_delivery_bookkeeping(name, required):
    body = text(f".opencode/agents/{name}.md")
    assert required in body
    for example in re.findall(r"```json\n(.*?)\n```", body, re.S):
        payload = json.loads(example)
        assert not {"format_only", "delivery_state", "correction_used", "route"} & payload.keys()


def test_canonical_doc_discloses_prospective_gate_and_evidence_limits():
    doc = section("docs/dev/features/opencode-agent-workflow.md", "#### Fail-closed delivery: prospective acceptance")
    for term in ("AGENTS.md#fail-closed-handoff-delivery", "old ten and five", "FAILED", "not rescored",
                 "Strip the markdown fences only as a mechanical delivery repair", "baseline 2",
                 "baseline 4", "no improvement claim", "five guided", "one original-author",
                 "120", "180", "BLOCKED", "not successful repair or task approval",
                 "not hard runtime enforcement", "controller-owned"):
        assert term in doc
