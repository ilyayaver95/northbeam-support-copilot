"""evals/ — the behavioural test suite for the copilot.

Six categories, each isolating one way the system can be wrong:

    policy_lookup     read a fact off the policy corpus, when the question and
                      the document share no vocabulary
    synthesis         combine facts that live in two or more documents
    tool_use          call the right tool with the right id
    investigation     pull records and reach the right conclusion, including
                      the cases where the shallow read is wrong
    honesty           report that a record is missing or a value is not
                      retained, without fabricating and without over-declining
    boundaries        decline what should be declined — protected values,
                      out-of-scope advice, actions there is no tool for — and
                      NOT decline what merely sounds like it

Grading is deterministic and binary per case: substring, citation and tool-call
checks against the structured Answer. No LLM judges anything.

    python -m evals.runner investigation
    python -m evals.run_all --save after.json
"""
