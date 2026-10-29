"""Test-only illustration of the canonical handoff-recovery routing policy.

This module is a test-only illustration of the canonical fail-closed
handoff delivery contract's recovery decisioning with explicit fixture
facts only. It performs no I/O, imports no production modules and makes
no enforcement claim: source guards, offline
fixture examples and virtual routing probes are not runtime enforcement.
`route_recovery(facts) -> str` returns a closed routing label (documented in
the contract test module) and is used by that test file only.
"""

DELIVERY_STATES = ("eligible", "format_repair", "quarantined", "excluded")

ASSESSMENTS = ("missing", "unusable", "usable_adverse", "usable_ok")

BOOLEAN_KEYS = (
    "snapshot_verified",
    "ancestry_recorded",
    "independent_work_required",
    "findings_preserved",
    "pending_consultations_preserved",
    "global_constraints_preserved",
    "whole_range_review_required",
    "changed_strategy_recorded",
    "actual_resource_exhaustion",
    "unavailable_evidence_after_diagnosis",
    "permitted_productive_step",
    "human_boundary",
)

COUNTER_KEY = "failures_same_signature"

# Records required before replacement dispatch may be authorized on a
# quarantined delivery (verified snapshot, immutable ancestry, independence and
# inherited obligations).
REPLACEMENT_OBLIGATION_KEYS = (
    "snapshot_verified",
    "ancestry_recorded",
    "independent_work_required",
    "findings_preserved",
    "pending_consultations_preserved",
    "global_constraints_preserved",
    "whole_range_review_required",
)


def validate_facts(facts):
    """Validate one fixture against the closed facts schema.

    Raises ``ValueError`` for unknown or missing keys, unknown enum values,
    non-bool values for strict boolean keys, non-integer or negative counter
    values, bool-as-integer counters, and contradictory state/assessment
    combinations.
    """
    if not isinstance(facts, dict):
        raise ValueError("fixture facts must be a dict of explicit facts")
    required = set(BOOLEAN_KEYS) | {COUNTER_KEY, "state", "assessment"}
    unknown = sorted(set(facts) - required)
    if unknown:
        raise ValueError(f"unknown fixture keys: {unknown}")
    missing = sorted(required - set(facts))
    if missing:
        raise ValueError(f"missing fixture keys: {missing}")
    if facts["state"] not in DELIVERY_STATES:
        raise ValueError(f"unknown delivery_state: {facts['state']!r}")
    if facts["assessment"] not in ASSESSMENTS:
        raise ValueError(f"unknown assessment: {facts['assessment']!r}")
    counter = facts[COUNTER_KEY]
    if isinstance(counter, bool) or not isinstance(counter, int):
        raise ValueError("failures_same_signature must be a strict integer, not bool")
    if counter < 0:
        raise ValueError("failures_same_signature must be nonnegative")
    for key in BOOLEAN_KEYS:
        if not isinstance(facts[key], bool):
            raise ValueError(f"{key} must be a strict bool")
    usable = facts["assessment"] in ("usable_ok", "usable_adverse")
    if facts["state"] == "eligible" and not usable:
        raise ValueError("an eligible delivery cannot carry a missing/unusable assessment")
    if facts["state"] == "quarantined" and usable:
        raise ValueError("a quarantined delivery cannot carry a usable assessment")
    if facts["state"] == "format_repair" and usable:
        raise ValueError("a format_repair delivery cannot carry a usable assessment")


def route_recovery(facts):
    """Route one fixture per the canonical contract precedence.

    Preconditions: ``validate_facts`` contract holds. Precedence:

    1. actual human boundaries and excluded expert/wrapper outputs follow their
       existing routes;
    2. evidenced actual resource/evidence blockers or no permitted productive
       step produce truthful incomplete status (never approval, never a routine
       human permission request);
    3. eligible usable assessments resume normal handling — adverse findings
       keep the ordinary fix/consultation/adjudication routes and are never
       replaceable;
    4. a format_repair delivery spends its single same-author allowance, or is
       quarantined once spent (no second request);
    5. a quarantined delivery requires recorded snapshot verification, immutable
       ancestry, independence and every inherited obligation before dispatch;
       missing records block only the dispatch while gathered autonomously;
    6. at two or more task-wide failures with the same signature, a concrete
       changed strategy is required before dispatch (blind retries refused, the
       task continues);
    7. otherwise the controller-owned same-range replacement dispatch runs.
    """
    validate_facts(facts)
    if facts["human_boundary"] or facts["state"] == "excluded":
        return "existing_boundary_route"
    if facts["state"] == "eligible":
        return "normal_handling"
    blocked = (facts["actual_resource_exhaustion"]
               or facts["unavailable_evidence_after_diagnosis"]
               or not facts["permitted_productive_step"])
    if blocked:
        return "truthful_incomplete_stop"
    if facts["state"] == "format_repair":
        if facts["assessment"] == "missing":
            return "format_correction"
        return "quarantine_delivery"
    if any(not facts[key] for key in REPLACEMENT_OBLIGATION_KEYS):
        return "autonomous_evidence_gathering"
    if facts[COUNTER_KEY] >= 2 and not facts["changed_strategy_recorded"]:
        return "changed_strategy_required"
    return "replacement_dispatch"


def _facts(state, assessment, **overrides):
    facts = {key: True for key in BOOLEAN_KEYS}
    facts.update(
        actual_resource_exhaustion=False,
        unavailable_evidence_after_diagnosis=False,
        permitted_productive_step=True,
        human_boundary=False,
        changed_strategy_recorded=False,
        state=state,
        assessment=assessment,
        failures_same_signature=0,
    )
    facts.update(overrides)
    return facts


CASES = [
    # Valid ordinary handling
    {"name": "eligible_verdict_resumes_normal_handling",
     "facts": _facts("eligible", "usable_ok"),
     "expected": "normal_handling"},
    # Adverse findings are not replaceable; review shopping refused
    {"name": "eligible_adverse_keeps_ordinary_fix_routes",
     "facts": _facts("eligible", "usable_adverse", independent_work_required=True),
     "expected": "normal_handling"},
    # Eligible first-format repair spends its single allowance
    {"name": "first_format_correction_spends_single_allowance",
     "facts": _facts("format_repair", "missing"),
     "expected": "format_correction"},
    # No second same-author request; the spent delivery is quarantined
    {"name": "second_format_request_refused_delivery_quarantined",
     "facts": _facts("format_repair", "unusable"),
     "expected": "quarantine_delivery"},
    # Quarantined unusable delivery replaced on the same range, below threshold
    {"name": "exhausted_delivery_replaced_same_range",
     "facts": _facts("quarantined", "unusable", failures_same_signature=1),
     "expected": "replacement_dispatch"},
    # Changed-fact quarantine, independent replacement with fresh source work
    {"name": "changed_facts_quarantined_replacement_with_independent_work",
     "facts": _facts("quarantined", "unusable", independent_work_required=True),
     "expected": "replacement_dispatch"},
    # Unavailable author: replace with genuine new worker work, no impersonation
    {"name": "unavailable_author_replaced_not_impersonated",
     "facts": _facts("quarantined", "missing", ancestry_recorded=True),
     "expected": "replacement_dispatch"},
    # Stale snapshot blocks dispatch until verified; evidence is autonomous
    {"name": "stale_snapshot_blocks_dispatch_until_verified",
     "facts": _facts("quarantined", "unusable", snapshot_verified=False),
     "expected": "autonomous_evidence_gathering"},
    # Lost global-constraints record delays replacement, not recovery
    {"name": "lost_global_constraints_recorded_before_dispatch",
     "facts": _facts("quarantined", "unusable", global_constraints_preserved=False),
     "expected": "autonomous_evidence_gathering"},
    # Lost whole-range coverage record delays replacement for the full range
    {"name": "lost_whole_range_coverage_recorded_before_dispatch",
     "facts": _facts("quarantined", "unusable", whole_range_review_required=False),
     "expected": "autonomous_evidence_gathering"},
    # Task-wide counts persist across authors/subtasks; blind retry refused
    {"name": "task_wide_count_retention_refuses_blind_retry",
     "facts": _facts("quarantined", "unusable", failures_same_signature=2),
     "expected": "changed_strategy_required"},
    # Changed strategy recorded: same threshold continues the task
    {"name": "changed_strategy_continues_task_at_threshold",
     "facts": _facts("quarantined", "unusable", failures_same_signature=2,
                     changed_strategy_recorded=True),
     "expected": "replacement_dispatch"},
    # Evidenced actual resource exhaustion stops truthfully, not approval
    {"name": "actual_resource_exhaustion_truthful_incomplete",
     "facts": _facts("quarantined", "unusable", actual_resource_exhaustion=True),
     "expected": "truthful_incomplete_stop"},
    # Evidence unavailable after permitted diagnosis: incomplete, no loop
    {"name": "unavailable_evidence_after_diagnosis_truthful_incomplete",
     "facts": _facts("quarantined", "unusable",
                     unavailable_evidence_after_diagnosis=True,
                     permitted_productive_step=False),
     "expected": "truthful_incomplete_stop"},
    # No permitted productive step: incomplete status, no retry authorization
    {"name": "no_permitted_productive_step_truthful_incomplete",
     "facts": _facts("quarantined", "unusable", permitted_productive_step=False),
     "expected": "truthful_incomplete_stop"},
    # Actual human boundary follows its existing route first
    {"name": "human_boundary_follows_existing_route",
     "facts": _facts("quarantined", "unusable", human_boundary=True),
     "expected": "existing_boundary_route"},
    # Excluded expert answers and capability wrapper outputs stay out of repair
    {"name": "excluded_expert_or_wrapper_route",
     "facts": _facts("excluded", "unusable"),
     "expected": "existing_boundary_route"},
]
