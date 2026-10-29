"""Source-contract guards plus a labelled test-only recovery routing model.

These guards cover the canonical `Autonomous operational recovery` guidance in
`AGENTS.md#fail-closed-handoff-delivery`, its concise controller/skill hooks,
the canonical documentation section and the Makefile registration, while
preserving the original role formats and the frozen evaluator experiment. The
`handoff_recovery_model` module is a separately labelled illustration: explicit
fixture facts only, no I/O, no production-module imports and no enforcement
claim; guards, fixtures and offline examples are not runtime enforcement.

Route outputs use closed strings mirroring the contract:
- ``existing_boundary_route``: human boundaries/excluded expert and wrapper
  outputs follow their existing routes, never recovery.
- ``normal_handling``: preflight-eligible delivery with a usable assessment
  resumes ordinary semantic handling; adverse findings keep the ordinary fix,
  consultation and adjudication routes and are never replaceable.
- ``format_correction``: the single same-author format-only allowance spent.
- ``quarantine_delivery``: refuse a second same-author request; quarantine the
  delivery and recover the task under replacement rules.
- ``truthful_incomplete_stop``: evidenced actual resource/evidence blockers or
  no permitted productive step, reported as incomplete status, not approval.
- ``autonomous_evidence_gathering``: missing obligation records block only the
  replacement dispatch while they are gathered autonomously, not human
  permission.
- ``changed_strategy_required``: threshold reached; refuse unchanged blind
  retries until a concrete changed strategy is recorded.
- ``replacement_dispatch``: controller-owned same-range independent
  replacement authorized to complete a missing/unusable assessment.
"""
import copy
from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]

CONTROLLERS = ("supervisor", "fast-dev", "live-dev")
SKILLS = {
    "subagent-driven-development": "## Pending consultation handler",
    "systematic-debugging": "## The Iron Law",
    "fast-dev-wrap-up": "## Bounded consultation",
}

DOC_HEADING = "#### Autonomous handoff recovery: controller-owned replacement"


def text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def section(path, heading):
    body = text(path).split(heading + "\n", 1)
    assert len(body) == 2, f"{path}: missing {heading}"
    level = len(heading.split(" ", 1)[0])
    return " ".join(re.split(rf"\n#{{1,{level}}} ", body[1], maxsplit=1)[0].split())


def test_canonical_autonomous_recovery():
    rule = section("AGENTS.md", "### Fail-closed handoff delivery")
    for term in ("Autonomous operational recovery", "same verified branch and base/head range",
                 "immutable failure ancestry", "Reject the unusable delivery, not the overall task",
                 "untrusted lead", "truthful incomplete"):
        assert term in rule


def test_canonical_recovery_routing_terms():
    rule = section("AGENTS.md", "### Fail-closed handoff delivery")
    for term in ("replacement work", "quarantine", "task-wide",
                 "failures with the same signature", "changed strategy", "review shopping",
                 "ordinary fixes, consultation and adjudication", "evidence gathering",
                 "not a human permission question", "not approval",
                 "no artificial commit or range change"):
        assert term in rule, f"canonical recovery rule missing {term!r}"


@pytest.mark.parametrize("name", CONTROLLERS)
def test_controller_gates_reference_autonomous_recovery(name):
    hook = section(f".opencode/agents/{name}.md", "## Handoff delivery gate (before all report handling)")
    for term in ("AGENTS.md#fail-closed-handoff-delivery",
                 "Autonomous operational recovery", "replacement work", "same verified branch and base/head range",
                 "immutable failure ancestry", "not a budget reset", "truthful incomplete"):
        assert term in hook, f"{name}: gate missing {term!r}"


@pytest.mark.parametrize("name", sorted(SKILLS))
def test_skill_preflights_reference_autonomous_recovery_before_transitions(name):
    path = f".opencode/skills/{name}/SKILL.md"
    hook = section(path, "## Handoff delivery preflight")
    for term in ("AGENTS.md#fail-closed-handoff-delivery",
                 "Autonomous operational recovery", "replacement work", "same verified branch and base/head range",
                 "immutable failure ancestry", "not a budget reset", "not approval"):
        assert term in hook, f"{name}: preflight missing {term!r}"
    body = text(path)
    assert body.index("## Handoff delivery preflight") < body.index(SKILLS[name])


def test_canonical_doc_has_recovery_heading_beside_frozen_history():
    doc = text("docs/dev/features/opencode-agent-workflow.md")
    frozen = "#### Fail-closed delivery: prospective acceptance"
    assert frozen in doc, "frozen fail-closed delivery history must remain intact"
    assert doc.index(frozen) < doc.index(DOC_HEADING)
    new = section("docs/dev/features/opencode-agent-workflow.md", DOC_HEADING)
    for term in ("AGENTS.md#fail-closed-handoff-delivery",
                 "Reject the unusable delivery", "same verified branch", "immutable failure ancestry",
                 "untrusted lead", "review shopping", "guided probes have not yet run",
                 "baseline probes", "test-only", "not runtime enforcement", "not approval",
                 "truthful incomplete", "restart"):
        assert term in new, f"docs recovery section missing {term!r}"


def test_makefile_registers_recovery_contract_tests():
    assert "scripts/tests/test_opencode_handoff_recovery_contract.py" in text("Makefile")


ROLE_FORMAT_KEEP = {
    "planner": "Otherwise return only raw Markdown suitable for PLAN.md",
    "implementer": "**Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT",
    "reviewer": "Return only one valid JSON object, with no Markdown fence",
    "debug-advisor": "Return only a single JSON object, no Markdown fence",
    "adjudicator": "Return only one valid JSON object, with no Markdown fence",
    "fast-dev-reviewer": "For this pending branch return only raw JSON, without a Markdown fence",
}


def test_original_role_formats_are_preserved():
    for name, marker in ROLE_FORMAT_KEEP.items():
        assert marker in text(f".opencode/agents/{name}.md"), name


def test_frozen_evaluator_experiment_is_not_extended():
    evaluator = text("scripts/eval_opencode_handoff_delivery.py")
    for anchor in ("QUESTION = ", "RUBRIC = ", "first-perfect gate remains FAILED"):
        assert anchor in evaluator, anchor
    assert "route_recovery" not in evaluator and "delivery_state" not in evaluator


def test_recovery_model_declares_test_only_scope_without_enforcement():
    model = text("scripts/tests/handoff_recovery_model.py")
    for anchor in ("test-only", "no I/O", "no enforcement claim", "route_recovery(facts) -> str"):
        assert anchor in model, anchor


def test_recovery_model_does_no_io_and_no_production_imports():
    model = text("scripts/tests/handoff_recovery_model.py")
    forbidden = ("import os", "import subprocess", "import socket", "import requests",
                 "urllib", "open(", "Path(", "AGENTS.md#", ".opencode/")
    for anchor in forbidden:
        assert anchor not in model, f"model must stay inert, found {anchor!r}"


# ---------------------------------------------------------------------------
# Test-only fixture routing model: closed schema and adversarial examples.
# No production module, no I/O and no enforcement claim is involved.
# ---------------------------------------------------------------------------

from handoff_recovery_model import (
    BOOLEAN_KEYS,
    CASES,
    REPLACEMENT_OBLIGATION_KEYS,
    route_recovery,
    validate_facts,
)


def valid_facts(**overrides):
    facts = {key: True for key in BOOLEAN_KEYS}
    facts.update(
        actual_resource_exhaustion=False,
        unavailable_evidence_after_diagnosis=False,
        permitted_productive_step=True,
        human_boundary=False,
        changed_strategy_recorded=False,
        state="quarantined",
        assessment="unusable",
        failures_same_signature=0,
    )
    facts.update(overrides)
    return facts


def test_recovery_examples_match_expected_routes():
    for case in CASES:
        assert route_recovery(copy.deepcopy(case["facts"])) == case["expected"], case["name"]


def test_every_example_fact_suite_is_schema_valid():
    for case in CASES:
        validate_facts(copy.deepcopy(case["facts"]))


def test_primary_enumerations_stay_closed():
    model = text("scripts/tests/handoff_recovery_model.py")
    assert 'DELIVERY_STATES = ("eligible", "format_repair", "quarantined", "excluded")' in model
    assert 'ASSESSMENTS = ("missing", "unusable", "usable_adverse", "usable_ok")' in model


def test_counter_must_be_a_nonnegative_strict_integer():
    for value in (True, "2", -1, 2.0, None):
        facts = valid_facts(failures_same_signature=value)
        with pytest.raises(ValueError):
            route_recovery(facts)
        with pytest.raises(ValueError):
            validate_facts(facts)


@pytest.mark.parametrize("key", sorted(BOOLEAN_KEYS))
@pytest.mark.parametrize("value", [1, 0, "yes", None])
def test_strict_booleans_reject_non_bool_values(key, value):
    facts = valid_facts(**{key: value})
    with pytest.raises(ValueError):
        route_recovery(facts)


@pytest.mark.parametrize("field,cross", [
    ("state", "missing"),
    ("assessment", "eligible"),
])
def test_unknown_enum_values_are_rejected(field, cross):
    for value in (1, "invalid", None, cross):
        facts = valid_facts(**{field: value})
        with pytest.raises(ValueError):
            route_recovery(facts)


def test_unknown_and_missing_keys_are_rejected():
    unknown = valid_facts(assessment="unusable") | {"verdict": "ok"}
    with pytest.raises(ValueError):
        route_recovery(unknown)
    for key in sorted(BOOLEAN_KEYS) + [REPLACEMENT_OBLIGATION_KEYS[0], "state", "assessment",
                                       "failures_same_signature"]:
        facts = valid_facts()
        facts.pop(key)
        with pytest.raises(ValueError):
            route_recovery(facts)


def test_non_dict_facts_are_rejected():
    for value in (None, [], "facts"):
        with pytest.raises(ValueError):
            route_recovery(value)


@pytest.mark.parametrize("facts", [
    valid_facts(state="eligible", assessment="missing"),
    valid_facts(state="eligible", assessment="unusable"),
    valid_facts(state="quarantined", assessment="usable_ok"),
    valid_facts(state="quarantined", assessment="usable_adverse"),
    valid_facts(state="format_repair", assessment="usable_ok"),
    valid_facts(state="format_repair", assessment="usable_adverse"),
])
def test_contradictory_state_assessment_combinations_are_rejected(facts):
    with pytest.raises(ValueError):
        route_recovery(facts)
    with pytest.raises(ValueError):
        validate_facts(facts)


def test_every_missing_obligation_record_blocks_dispatch_for_gathering():
    for key in REPLACEMENT_OBLIGATION_KEYS:
        facts = valid_facts()
        facts[key] = False
        assert route_recovery(facts) == "autonomous_evidence_gathering", key


def test_gathering_blocked_records_is_not_human_permission_nor_stop():
    facts = valid_facts(snapshot_verified=False, ancestry_recorded=False)
    assert route_recovery(facts) == "autonomous_evidence_gathering"
    assert route_recovery(facts) != "truthful_incomplete_stop"


def test_eligible_usable_assessment_is_never_replaceable():
    for assessment in ("usable_ok", "usable_adverse"):
        facts = valid_facts(state="eligible", assessment=assessment,
                            failures_same_signature=2, changed_strategy_recorded=True)
        assert route_recovery(facts) == "normal_handling", assessment
        assert route_recovery(facts) != "replacement_dispatch"


def test_adverse_shopping_refusal_survives_flipped_replacement_records():
    facts = valid_facts(state="eligible", assessment="usable_adverse")
    route = route_recovery(facts)
    flipped = copy.deepcopy(facts)
    flipped["snapshot_verified"] = False
    flipped["independent_work_required"] = False
    assert route == route_recovery(flipped) == "normal_handling"


def test_boundary_and_excluded_outputs_precede_replacement():
    boundary = valid_facts(human_boundary=True)
    excluded = valid_facts(state="excluded")
    assert route_recovery(boundary) == "existing_boundary_route"
    assert route_recovery(excluded) == "existing_boundary_route"
    # Even replacement-friendly facts do not leave the existing route.
    boundary["findings_preserved"] = True
    assert route_recovery(boundary) == "existing_boundary_route"


def test_second_format_request_refused_first_request_allowed():
    first = valid_facts(state="format_repair", assessment="missing")
    assert route_recovery(first) == "format_correction"
    spent = valid_facts(state="format_repair", assessment="unusable")
    refused = route_recovery(spent)
    assert refused == "quarantine_delivery"
    assert refused != "format_correction"


def test_truthful_stop_conditions_are_not_approval_nor_human_questions():
    for key, value in (("actual_resource_exhaustion", True),
                       ("unavailable_evidence_after_diagnosis", True),
                       ("permitted_productive_step", False)):
        facts = valid_facts(**{key: value})
        route = route_recovery(facts)
        assert route == "truthful_incomplete_stop", key
        assert route not in ("replacement_dispatch", "existing_boundary_route"), key


def test_actual_blockers_stop_before_gathering_missing_records():
    facts = valid_facts(actual_resource_exhaustion=True)
    facts["snapshot_verified"] = False
    facts["global_constraints_preserved"] = False
    assert route_recovery(facts) == "truthful_incomplete_stop"


def test_threshold_requires_changed_strategy_and_refuses_blind_retry():
    at_threshold = valid_facts(failures_same_signature=2)
    assert route_recovery(at_threshold) == "changed_strategy_required"
    assert route_recovery(at_threshold) != "replacement_dispatch"
    # Unchanged strategy at higher counts also stays refused, never auto-stop.
    above = valid_facts(failures_same_signature=5)
    assert route_recovery(above) == "changed_strategy_required"


def test_recorded_changed_strategy_continues_the_task():
    keep = valid_facts(failures_same_signature=2, changed_strategy_recorded=True)
    below = valid_facts(failures_same_signature=1)
    zero = valid_facts()
    for facts in (keep, below, zero):
        assert route_recovery(facts) == "replacement_dispatch", facts


def test_missing_obligation_precedes_threshold_strategy_check():
    facts = valid_facts(failures_same_signature=3)
    facts["whole_range_review_required"] = False
    assert route_recovery(facts) == "autonomous_evidence_gathering"
