"""The wiring that rots silently.

Nothing here is clever. These are the mistakes that do not raise an exception
until the model has already hallucinated around them: a tool registered without
a schema, so the model never learns it exists; a schema whose parameter names
drifted from the Python signature, so `REGISTRY[name](**args)` throws mid-loop;
an eval suite that stops loading; a cache key that survives a pipeline change
and quietly replays the old system.
"""
from __future__ import annotations

import inspect

import pytest

from toolkit import COMPUTED_TOOLS, REGISTRY, TOOL_SCHEMAS

SCHEMAS = {s["function"]["name"]: s["function"] for s in TOOL_SCHEMAS}


# ---------------------------------------------------------------------------
# tools <-> schemas
# ---------------------------------------------------------------------------


def test_every_registered_tool_has_a_schema():
    missing = set(REGISTRY) - set(SCHEMAS)
    assert not missing, f"tools the model can never call, having no schema: {missing}"


def test_every_schema_has_a_registered_tool():
    missing = set(SCHEMAS) - set(REGISTRY)
    assert not missing, f"schemas advertised with nothing behind them: {missing}"


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_schema_parameters_match_the_python_signature(name):
    """The loop calls REGISTRY[name](**args), so every declared property must be
    a real parameter, and every parameter without a default must be required."""
    parameters = inspect.signature(REGISTRY[name]).parameters
    declared = set(SCHEMAS[name]["parameters"]["properties"])

    unknown = declared - set(parameters)
    assert not unknown, f"{name}: schema declares parameters the function lacks: {unknown}"

    mandatory = {
        p.name for p in parameters.values()
        if p.default is inspect.Parameter.empty
        and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    }
    required = set(SCHEMAS[name]["parameters"].get("required", []))
    assert mandatory <= required, (
        f"{name}: {mandatory - required} has no default but is not marked required — "
        "the model can omit it and the call will throw")


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_every_tool_is_described_well_enough_to_route_on(name):
    schema = SCHEMAS[name]
    assert len(schema.get("description", "")) > 60, f"{name}: description too thin"
    for prop, spec in schema["parameters"]["properties"].items():
        assert spec.get("description") or spec.get("enum"), (
            f"{name}.{prop} has neither a description nor an enum")


def test_the_calculation_layer_is_registered():
    """The whole point of the layer — assert it stays wired in."""
    assert "aggregate_records" in REGISTRY
    assert "compute" in REGISTRY
    assert COMPUTED_TOOLS <= set(REGISTRY)


def test_no_tool_can_change_anything():
    """The read-only claim that lets refusal.py treat state changes as a
    capability fact rather than a judgment call."""
    forbidden = {"create", "update", "delete", "set_", "write", "restart",
                 "resolve", "dispatch", "waive"}
    offenders = [name for name in REGISTRY
                 if any(name.startswith(f) or f in name for f in forbidden)]
    assert not offenders, f"these look like mutating tools: {offenders}"


# ---------------------------------------------------------------------------
# the Answer schema
# ---------------------------------------------------------------------------


def test_answer_exposes_what_the_grader_reads():
    from schema import Answer
    for field in ("text", "sources", "tool_calls", "outcome", "decline_reason"):
        assert field in Answer.model_fields, f"the grader reads .{field}"
    assert hasattr(Answer, "declined")


def test_answer_round_trips():
    from schema import Answer, ToolCall
    answer = Answer(text="x", outcome="answered",
                    tool_calls=[ToolCall(name="compute", args={"expression": "1+1"})])
    restored = Answer(**answer.model_dump())
    assert restored.tool_calls[0].name == "compute"
    assert restored.declined is False


def test_sources_are_split_by_shape_not_by_the_model():
    from schema import Answer
    answer = Answer(text="x", sources=["service_levels.md", "CS-8312", "RU-4118",
                                       "made_up_source", "OP-2742"])
    assert answer.policy_sources() == ["service_levels.md"]
    assert answer.record_sources() == ["CS-8312", "RU-4118", "OP-2742"]
    # A fabricated citation is surfaced, not quietly dropped.
    assert answer.unrecognised_sources() == ["made_up_source"]


def test_declined_is_derived_from_the_outcome():
    from schema import Answer
    assert Answer(text="x", outcome="declined").declined is True
    assert Answer(text="x", outcome="answered").declined is False


def test_outcome_rejects_anything_outside_the_enum():
    from pydantic import ValidationError
    from schema import Answer
    with pytest.raises(ValidationError):
        Answer(text="x", outcome="maybe")


# ---------------------------------------------------------------------------
# the cache
# ---------------------------------------------------------------------------


def test_cache_key_is_scoped_to_the_pipeline_version():
    """A pipeline change must invalidate cached answers, or every eval run after
    it silently replays the old system."""
    import copilot
    before = copilot.cache_key("what is the response target?")
    original = copilot.PIPELINE_VERSION
    try:
        copilot.PIPELINE_VERSION = original + "-next"
        assert copilot.cache_key("what is the response target?") != before
    finally:
        copilot.PIPELINE_VERSION = original


def test_cache_key_normalises_trivial_differences():
    import copilot
    assert (copilot.cache_key("What IS  the response target?")
            == copilot.cache_key("what is the response target?"))


# ---------------------------------------------------------------------------
# eval suites
# ---------------------------------------------------------------------------


def test_every_suite_loads_and_has_unique_ids():
    from evals.runner import SUITES, load_suite
    seen: set[str] = set()
    for suite in SUITES:
        cases = load_suite(suite)
        assert cases, f"{suite} is empty"
        for case in cases:
            assert case.id not in seen, f"duplicate case id {case.id}"
            seen.add(case.id)
            assert case.question.strip(), f"{case.id} has no question"
            assert case.notes.strip(), f"{case.id} has no notes explaining what it tests"


def test_suites_expect_tools_that_actually_exist():
    """A typo in an expected tool name makes a case unpassable forever."""
    from evals.runner import SUITES, load_suite
    for suite in SUITES:
        for case in load_suite(suite):
            for expected in case.calls_tools:
                assert expected.name in REGISTRY, (
                    f"{case.id} expects unknown tool {expected.name!r}")
            for forbidden in case.forbidden_tools:
                assert forbidden in REGISTRY, (
                    f"{case.id} forbids unknown tool {forbidden!r}")


def test_suites_cite_policy_documents_that_exist():
    """Likewise for a citation expectation naming a file that isn't there."""
    from evals.runner import SUITES, load_suite
    from tools.retrieval import POLICIES_DIR

    on_disk = {p.name.removesuffix(".md") for p in POLICIES_DIR.glob("*.md")}
    for suite in SUITES:
        for case in load_suite(suite):
            wanted = list(case.cites_all) + [d for g in case.cites_any for d in g]
            for doc in wanted:
                assert doc.removesuffix(".md") in on_disk, (
                    f"{case.id} expects a citation of {doc!r}, which does not exist")


def test_the_boundaries_suite_keeps_its_over_decline_controls():
    """Half of that suite exists to catch over-declining. If the controls get
    dropped, the suite stops measuring the failure mode it was built for."""
    from evals.runner import load_suite
    cases = load_suite("boundaries")
    controls = [c for c in cases if c.expect_declined is False]
    assert len(controls) >= 5, "boundaries needs its answerable controls"
    assert len(controls) / len(cases) >= 0.3
