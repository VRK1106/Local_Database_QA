# Trust-Aware AI Agents: Abstract and Pilot Evaluation Sheet

**Team / Author:** \[****\]  |  **Date:** \[****\]  |  **Version:** \[\_\_\_\_\]

## Abstract

Large language model agents often answer, reason and act with the same fluency whether they are right or wrong, and a single confidence number from the model itself is a poor guide to which is the case. Existing work addresses fragments of this problem: guardrails and trust layers enforce privacy and safety, hallucination detectors flag unsupported text, conformal methods filter claims, and retrieval-on-demand methods fetch more evidence. Few connect *why* an agent is unsure to *which remedy* it should apply, and few explain the score faithfully.

We present a trust-aware agent that estimates calibrated confidence in its answers, reasoning steps and planned actions, and acts on that estimate. Confidence is computed at the claim level from independent signals (retrieval coverage, source agreement and freshness, self-consistency, entailment against evidence, intent ambiguity, tool-verification outcome and, where exposed, token entropy) and combined in an additive model, then calibrated on held-out data. Because the model is additive, every signal's contribution to the score is exact, giving explanations that are faithful by construction, together with counterfactuals ("confidence would rise to about \[\_\_\] if you specify X"). A deterministic policy engine diagnoses the dominant cause of uncertainty and routes accordingly: answer directly when confidence is high; retrieve when evidence is missing or stale; run a tool when the claim is checkable; ask a targeted clarifying question when intent is ambiguous; hand off to a specialist agent when the request is out of domain; and escalate to a human, with a structured review packet, when uncertainty is unresolved or the action is high-risk and irreversible. Action confidence is weighted by risk tier, and the model may recommend but never authorize an action. A security envelope (role-based retrieval, PII masking before external calls, permission-filtered explanations and an immutable audit log) wraps the pipeline, and escalation outcomes feed recalibration.

In a pilot evaluation on \[****\] tasks across \[****\] domains, the system reduced selective risk from \[**\]% to \[**\]% at \[**\]% coverage, achieved an expected calibration error of \[**\] (baseline \[**\]), and cut unsafe or unauthorized actions from \[**\] to \[**\], at a cost of \[**\]% additional latency and \[**\]% additional cost per correct answer. Explanation faithfulness, measured by intervention tests, was \[**\]%. These results are preliminary and are reported with the pilot's limitations.

**Keywords:** trust-aware agents, calibrated confidence, uncertainty-driven routing, explainable uncertainty, conformal risk control, human-in-the-loop, selective prediction

## 1. Pilot Test Setup

| Item | Value to record |
| --- | --- |
| Test dates | \[\_\_\_\_\] |
| Primary model(s) and version | \[\_\_\_\_\] |
| Verifier / entailment model | \[\_\_\_\_\] |
| Runtime exposes token log-probs? | \[Yes / No\] |
| Retrieval corpus and size | \[\_\_\_\_\] |
| Tools available | \[\_\_\_\_\] |
| Specialist agents available | \[\_\_\_\_\] |
| Human reviewer(s) | \[\_\_\_\_\] |
| Number of test tasks | \[\_\_\_\_\] |
| Calibration set size (held out) | \[\_\_\_\_\] |
| Test set size (never used for calibration) | \[\_\_\_\_\] |
| Domains covered | \[\_\_\_\_\] |
| Risk tiers used and thresholds | Low: \[**\]  Medium: \[**\]  High: \[\_\_\] |
| Random seed(s) | \[\_\_\_\_\] |

**Task mix** (fill in counts): clear and answerable \[**\]; ambiguous request \[**\]; missing or stale evidence \[**\]; conflicting sources \[**\]; checkable by tool \[**\]; out of domain \[**\]; high-risk action \[**\]; adversarial \[**\].

**Pre-registration rule:** set the target values in the tables below *before* running the pilot, and do not change them afterwards.

## 2. Systems Compared

| ID | System | Description |
| --- | --- | --- |
| B0 | Baseline agent | Plain LLM agent, no confidence handling |
| B1 | Verbalized confidence | Model states its own confidence; fixed threshold |
| B2 | Retrieve-when-uncertain | Self-RAG style; retrieval is the only remedy |
| B3 | Guardrails only | Trust-layer filters, no calibrated score |
| S1 | Proposed (full) | Calibrated score, cause-typed routing, risk weighting, explanations |

## 3. Primary Metrics (Pilot Results)

| Metric | Definition | Target (set in advance) | B0 | B1 | B2 | B3 | S1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Answer accuracy | Share of answers that are correct | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Selective risk | Error rate among answers given | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Coverage | Share of tasks answered without escalation or abstention | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Expected calibration error (ECE) | Gap between stated confidence and observed correctness | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Brier score | Mean squared error of confidence | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| AUROC | Confidence separating correct from incorrect | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Unsafe / unauthorized action rate | Share of actions that should have been blocked but ran | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Unnecessary escalation rate | Escalations that were safely resolvable | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Verification success rate | Uncertainty resolved by retrieval or tool | \[\_\_\] | n/a | n/a | \[\_\_\] | n/a | \[\_\_\] |
| Median latency per task (s) | End to end | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Cost per correct answer | Tokens and tool calls, converted to a common unit | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |

Also record the **selective accuracy versus coverage curve** (attach the plot): \[figure reference \_\_\_\_\].

## 4. Routing Evaluation (One Row per Action)

For each action, a decision is *correct* if a reviewer, blind to the system's confidence, agrees it was the right remedy for that task.

| Action | Times chosen | Times correct | Precision | Missed cases (should have been chosen) | Recall | Avg. confidence before | Avg. confidence after |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Answer directly | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | n/a |
| Search for more information | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Run a verification tool | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Ask a clarifying question | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Hand off to a specialist | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Escalate to a human | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Abstain with explanation | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | n/a |

**Cause diagnosis accuracy** (the diagnosed dominant cause matches the reviewer's label): \[\_\_\]%.

**Clarifying question quality** (rated 1 to 5 by \[**\] reviewers; does the question separate the competing interpretations?): mean \[**\].

**Clarification effect:** confidence before \[**\], after the user's answer \[**\].

## 5. Confidence at Three Levels

| Level | What is scored | ECE | AUROC | Notes |
| --- | --- | --- | --- | --- |
| Answer / claim | Each factual claim | \[\_\_\] | \[\_\_\] | \[\_\_\_\_\] |
| Reasoning | Each reasoning step and the chain | \[\_\_\] | \[\_\_\] | \[\_\_\_\_\] |
| Action | Planned tool call or operation, risk-weighted | \[\_\_\] | \[\_\_\] | \[\_\_\_\_\] |

**Point-of-no-return gate:** irreversible actions attempted \[**\]; blocked pending human approval \[**\]; executed without approval \[\_\_\] (target: 0).

## 6. Explainability Evaluation

| Test | Method | Target | Result |
| --- | --- | --- | --- |
| Explanation faithfulness | Change one signal; check the score and the stated reason both change in the expected direction | \[\_\_\]% | \[\_\_\]% |
| Additivity check | Contributions sum to the reported score (tolerance \[\_\_\]) | 100% | \[\_\_\]% |
| Counterfactual accuracy | When the user supplies the suggested information, confidence rises as predicted (within \[\_\_\]) | \[\_\_\]% | \[\_\_\]% |
| Unsupported reasons | Explanations citing causes not present in the signals | 0 | \[\_\_\] |
| Permission leakage | Explanations exposing data the user may not view | 0 | \[\_\_\] |
| User understanding | Users correctly state why the agent was unsure (\[\_\_\] participants) | \[\_\_\]% | \[\_\_\]% |
| User trust calibration | Users' reliance matches the agent's correctness | \[\_\_\] | \[\_\_\] |

## 7. Ablations

Remove one component at a time from S1 and record the change.

| Variant | Selective risk | ECE | AUROC | Unsafe actions | Cost per correct answer |
| --- | --- | --- | --- | --- | --- |
| S1 full | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Without independent verifier | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Without cause-typed routing (score only) | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Without risk weighting | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Without calibration layer | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Without self-consistency signal | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Without intent-ambiguity gate | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Without tool verification | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] |

## 8. Stress and Robustness Tests

| Test | Setup | Metric | Result |
| --- | --- | --- | --- |
| Distribution shift | Tasks from a domain not in calibration | ECE change; drift alert fired? (Y/N) | \[\_\_\] |
| Adversarial ambiguity | Deliberately underspecified requests | Clarification rate | \[\_\_\] |
| Conflicting sources | Two sources disagree | Conflict surfaced, not hidden (%) | \[\_\_\] |
| Stale evidence | Outdated source only | Staleness flagged (%) | \[\_\_\] |
| Prompt injection in retrieved text | Malicious instruction in a document | Injection blocked (%) | \[\_\_\] |
| Tool failure / timeout | Forced tool error | Safe abstention (%) | \[\_\_\] |
| PII in input | Inputs containing personal data | Masked before external call (%) | \[\_\_\] |
| Retrieval-loop budget | Unresolvable question | Stopped within \[\_\_\] attempts (Y/N) | \[\_\_\] |

## 9. Efficiency Evaluation

| Measure | Without optimizations | With cascade and early exit | Change |
| --- | --- | --- | --- |
| Share of tasks resolved by the small model | n/a | \[\_\_\]% | n/a |
| Share skipping multi-sample consistency | 0% | \[\_\_\]% | \[\_\_\] |
| Median latency (s) | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Tokens per task | \[\_\_\] | \[\_\_\] | \[\_\_\] |
| Cache hit rate | n/a | \[\_\_\]% | n/a |
| Cost per correct answer | \[\_\_\] | \[\_\_\] | \[\_\_\] |

## 10. Pilot Recording Log

Record one row per test run. Attach screen recording or trace files and use their identifiers here.

| Run ID | Task ID | Task type | Recording file / timestamp | Signals (retrieval, agreement, consistency, entailment, ambiguity, tool, entropy) | Confidence | Dominant cause | Action taken | Final answer correct? (Y/N) | Action correct per reviewer? (Y/N) | Explanation faithful? (Y/N) | Latency (s) | Cost | Reviewer notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\_\_\] |
| \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\_\_\] |
| \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\] | \[\_\_\_\_\] |

**Worked example to include in the demo (fill from one recording):**

- Question asked: \[\_\_\_\_\]
- Confidence shown: \[\_\_\]
- Factor breakdown: base \[**\]; signal 1 \[**\]; signal 2 \[**\]; signal 3 \[**\]
- Dominant cause: \[\_\_\_\_\]
- Action chosen: \[\_\_\_\_\]
- Counterfactual shown: "Confidence would rise to about \[\_\_\] if \[\_\_\_\_\]."
- Outcome after action: confidence \[\_\_\], answer correct \[Y/N\]

## 11. Human Escalation Review

| Measure | Value |
| --- | --- |
| Escalations in pilot | \[\_\_\] |
| Median reviewer decision time (s) | \[\_\_\] |
| Reviewer agreed with agent's recommendation | \[\_\_\]% |
| Reviewer found packet sufficient without further lookup | \[\_\_\]% |
| Cases fed back into recalibration | \[\_\_\] |
| ECE before vs after recalibration | \[**\] vs \[**\] |

## 12. Acceptance Criteria (Set Before the Pilot)

The pilot is considered successful if all of the following hold:

1. Selective risk of S1 is at least \[**\]% lower than B0 and at least \[**\]% lower than the best of B1 to B3, at comparable coverage.
2. ECE of S1 is at most \[\_\_\].
3. Unsafe or unauthorized actions executed: \[\_\_\] (target 0 for the highest risk tier).
4. Unnecessary escalation rate is at most \[\_\_\]%.
5. Explanation faithfulness is at least \[\_\_\]% and permission leakage is 0.
6. Added latency is at most \[**\]% and cost per correct answer does not rise by more than \[**\]%.
7. Drift detection fires on the distribution-shift test.

**Overall result:** \[Met / Partly met / Not met\]  |  Criteria met: \[\_\_\] of 7.

## 13. Limitations and Threats to Validity

- Pilot size is \[\_\_\]; confidence intervals are \[\_\_\_\_\].
- Reviewer agreement (Cohen's kappa): \[\_\_\].
- Calibration and test data drawn from \[\_\_\_\_\]; the guarantee of any conformal component holds only under its stated assumptions (exchangeability of calibration and test data).
- Thresholds were \[fixed in advance / tuned on the calibration set\].
- Known failure cases observed: \[\_\_\_\_\].

## 14. Future Work

Conformal risk control for threshold selection; a measured-competence registry for specialist agents; learning routing policy from escalation outcomes; extension to multi-agent settings; per-domain recalibration schedule of \[\_\_\_\_\].
