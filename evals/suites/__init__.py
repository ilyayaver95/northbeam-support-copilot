"""evals/suites/ — the cases, one module per category.

Every expected value here traces back to either a policy document or
`data/generated_facts.json`. Nothing is hand-copied from a model's output, which
is what keeps the suite a test of the system rather than a snapshot of it.

If the data is regenerated, re-check the `notes` on the aggregation cases — they
name the fact each expectation came from.
"""
