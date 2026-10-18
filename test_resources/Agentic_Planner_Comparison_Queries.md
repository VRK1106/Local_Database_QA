# Agentic Planner: Multi-Hop Comparison Queries

**Project:** Placement QA System (Flask, Ollama, ChromaDB, SQLite router)
**Extends:** The existing SQL router in `src/structured_query.py`
**Problem this solves:** Questions that require more than one query and a synthesis step — e.g. "Compare the average GPA of students who know React vs. those who know Angular" — currently either fail the aggregate regex and fall through to ungrounded semantic search, or cannot be expressed as a single query at all.

Confidence tags: **[Certain]** hard evidence, **[Likely]** strong inference, **[Guessing]** filling gaps.

---

## 0. Read This First

This is an extension of the SQL router, not a new subsystem next to it. **[Certain]** It must not become its own unvalidated layer — the golden dataset from step 1 of the broader plan has to be extended to cover these questions before you trust any result this produces. Do not evaluate this by eyeballing outputs. A confidently wrong comparison is a worse failure than the current fallback, because it looks more rigorous than it is.

**Scope boundary, deliberately narrow:** this plan covers **two-way comparison queries with a shared aggregate** (compare metric X across two groups defined by a categorical filter). It does not cover arbitrary multi-step reasoning, joins across unrelated tables, or open-ended "explore my data" agents. Widening scope beyond this is where agentic RAG projects burn weeks without a working demo. **[Likely]**

---

## 1. Why a Planner and Not a Bigger Regex

The current `is_aggregate_query()` router (per the evaluation report) matches single-aggregate patterns like `COUNT(*) WHERE cgpa > 8.0`. A comparison question needs two things the regex can't give you:

1. **Decomposition** — splitting "compare X between A and B" into two independent, well-formed queries.
2. **Synthesis** — computing the difference/ratio and phrasing it, which is a job for the LLM once it has two exact numbers, not for SQL.

Extending the regex to catch comparison phrasing without decomposition would still only get you as far as a single ambiguous query, which is exactly the failure mode you're trying to remove. A lightweight planning step is the right fix. **[Likely]**

---

## 2. Architecture

```
Question
   │
   ▼
┌─────────────────────────┐
│  Query Classifier        │  existing is_aggregate_query() + a new
│                          │  is_comparison_query() check
└───────────┬──────────────┘
            │ comparison detected
            ▼
┌─────────────────────────┐
│  Planner (LLM, temp=0)   │  decomposes into a fixed JSON schema:
│                          │  {metric, group_column, group_values[2],
│                          │   filters[]}
└───────────┬──────────────┘
            │ validated plan
            ▼
┌─────────────────────────┐
│  Sub-Query Executor       │  builds 2 parameterized SQL templates
│  (deterministic, no LLM   │  from the plan — never lets the LLM
│   SQL generation)         │  write SQL directly
└───────────┬──────────────┘
            │ two exact numeric results
            ▼
┌─────────────────────────┐
│  Synthesis (LLM, temp=0) │  given ONLY the two numbers + labels,
│                          │  writes the comparison sentence
└───────────┬──────────────┘
            ▼
┌─────────────────────────┐
│  Trust Layer (existing)  │  checks the synthesis sentence against
│                          │  the two numbers it was given
└─────────────────────────┘
```

**Rule that must hold throughout: the LLM never writes SQL.** The planner outputs a constrained plan (a JSON object matched against a schema), and your code turns that plan into parameterized queries from a fixed set of templates. This is a direct continuation of what you already do correctly on the student-scoped path — do not regress it here just because the query is more complex. **[Certain]**

---

## 3. Step-by-Step Implementation

### 3.1 Detect comparison intent

```python
# src/comparison_query.py
import re

COMPARISON_PATTERNS = [
    r"\bcompare\b.*\b(vs|versus|and)\b",
    r"\bdifference between\b",
    r"\b(higher|lower|better|worse)\b.*\bthan\b",
]

def is_comparison_query(question: str) -> bool:
    q = question.lower()
    return any(re.search(p, q) for p in COMPARISON_PATTERNS)
```

Run this **before** `is_aggregate_query()`. A comparison question often also matches the single-aggregate regex on a substring, so ordering matters.

### 3.2 Planner prompt — constrained JSON output, not free SQL

```python
PLANNER_SYSTEM_PROMPT = """You convert a comparison question into a JSON plan.
Output ONLY valid JSON matching this schema, nothing else:

{
  "metric": "cgpa" | "backlog_count",
  "group_column": "known_skill" | "branch" | "batch_year",
  "group_a": "<value>",
  "group_b": "<value>",
  "aggregate": "avg" | "count" | "sum"
}

If the question cannot be expressed in this schema, output exactly: {"error": "unsupported"}
Do not include SQL. Do not include explanation. Do not include markdown fences.
"""
```

Call Ollama with `temperature=0.0` and the existing deterministic settings you already use elsewhere in the pipeline.

```python
def plan_comparison(question: str, model: str) -> dict:
    raw = call_ollama(PLANNER_SYSTEM_PROMPT, question, model=model, temperature=0.0)
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "unparseable"}
    return plan
```

### 3.3 Validate the plan before executing anything

**[Certain]** This is the step most agentic-RAG tutorials skip, and it's the one that matters most. Never execute a plan you haven't checked against an allowlist.

```python
ALLOWED_METRICS = {"cgpa", "backlog_count"}
ALLOWED_GROUP_COLUMNS = {"known_skill", "branch", "batch_year"}

def validate_plan(plan: dict) -> tuple[bool, str]:
    if "error" in plan:
        return False, plan["error"]
    if plan.get("metric") not in ALLOWED_METRICS:
        return False, "unknown metric"
    if plan.get("group_column") not in ALLOWED_GROUP_COLUMNS:
        return False, "unknown group column"
    if not plan.get("group_a") or not plan.get("group_b"):
        return False, "missing group values"
    if plan.get("aggregate") not in {"avg", "count", "sum"}:
        return False, "unknown aggregate"
    # Confirm the group values actually exist in the data before querying.
    if not value_exists(plan["group_column"], plan["group_a"]):
        return False, f"no students found for {plan['group_a']}"
    if not value_exists(plan["group_column"], plan["group_b"]):
        return False, f"no students found for {plan['group_b']}"
    return True, ""
```

If validation fails, return a clear refusal ("I can't answer that comparison — try rephrasing with a specific skill, branch, or batch year") instead of guessing. A refusal is a better outcome than a wrong number. **[Certain]**

### 3.4 Execute two fixed templates, never LLM-generated SQL

```python
TEMPLATE = {
    "avg": "SELECT AVG({metric}) AS result, COUNT(*) AS n FROM students WHERE {group_column} = ?",
    "count": "SELECT COUNT(*) AS result FROM students WHERE {group_column} = ?",
    "sum": "SELECT SUM({metric}) AS result, COUNT(*) AS n FROM students WHERE {group_column} = ?",
}

def run_comparison(plan: dict) -> dict:
    sql = TEMPLATE[plan["aggregate"]].format(
        metric=plan["metric"], group_column=plan["group_column"]
    )
    result_a = query_only_connection.execute(sql, (plan["group_a"],)).fetchone()
    result_b = query_only_connection.execute(sql, (plan["group_b"],)).fetchone()
    return {
        "group_a": {"label": plan["group_a"], **dict(result_a)},
        "group_b": {"label": plan["group_b"], **dict(result_b)},
    }
```

Note that `metric` and `group_column` are interpolated from the **validated allowlist**, never from raw LLM text — the values themselves (`plan["group_a"]`, `plan["group_b"]`) go through the parameterized `?` placeholder, not string formatting. This keeps the same injection discipline you already applied to the student-scoped own-record query.

Run this against the same `PRAGMA query_only=ON` connection used elsewhere.

### 3.5 Synthesis — the LLM only sees numbers, never raw rows

```python
SYNTHESIS_PROMPT_TEMPLATE = """Given these two exact results, write one sentence comparing them.
Do not invent any numbers not given below. Do not mention students by name.

{group_a_label}: {group_a_result} (n={group_a_n})
{group_b_label}: {group_b_result} (n={group_b_n})
"""
```

Passing only the two aggregated numbers, not underlying student rows, is what keeps this from becoming a second channel for the same data-leakage risk covered in the RBAC work. A comparison feature that accidentally lets a student enumerate individual rows through group-by phrasing defeats the scoping you already built. **[Certain]**

### 3.6 Trust layer check on the synthesis step

Feed the DeBERTa cross-encoder the synthesis sentence against a reference statement built directly from the two numbers (e.g. `"Group A average is X, Group B average is Y, difference is Z"`). This is a stricter check than your existing retrieval-grounding check, because here you have exact ground truth, not retrieved passages. Flag any entailment score below your existing threshold. **[Likely]** worth doing since it's cheap given the trust layer already exists.

### 3.7 Wire it into `answer_query()`

```python
def answer_query(question, scope, top_k, model):
    if scope.sql_mode() == "full" and is_comparison_query(question):
        plan = plan_comparison(question, model)
        ok, reason = validate_plan(plan)
        if not ok:
            return refusal_response(reason)
        results = run_comparison(plan)
        answer = synthesize(results, model)
        trust_score = check_trust(answer, results)
        return build_response(answer, trust_score, sources=["structured_query"])
    if scope.sql_mode() == "full" and is_aggregate_query(question):
        ...  # existing single-aggregate path, unchanged
    ...  # existing semantic path, unchanged
```

**Scope restriction:** gate this on `scope.sql_mode() == "full"`, same as the existing aggregate path. The student scope never gets comparison queries across other students — only their own-record path stays available to them, unchanged from the RBAC plan.

---

## 4. Evaluation — extends, does not replace, item 1's golden dataset

Do not treat this as separately validated. Add a new question category to the golden dataset from the evaluation plan:

| Category | Example | Ground truth |
| :--- | :--- | :--- |
| Two-way comparison, avg | "Compare avg CGPA of React vs Angular students" | Computed directly from the mock data with pandas, independent of the app |
| Two-way comparison, count | "How many more students in CSE than ECE have backlogs?" | Same |
| Unsupported comparison | "Compare student satisfaction between branches" (no such column) | Expected: refusal, not a fabricated number |
| Ambiguous group value | "Compare toppers vs average students" | Expected: refusal, since "topper" isn't a defined category |
| Overlapping groups | "Compare React devs vs students with CGPA > 8" (not mutually exclusive) | Decide up front whether this is supported; if not, expected: refusal |

Compute exact-match accuracy on the numeric results, separately from whether the synthesis sentence reads correctly. A plan that computes the right numbers but phrases them badly is a different failure than a plan that computes the wrong numbers — track them separately so you know which part of the pipeline to fix.

**Minimum bar before calling this done:** the refusal cases must refuse. A comparison feature that answers overlapping or undefined groups with a confident, wrong number is worse than not having built it. **[Certain]**

---

## 5. Necessity and Impact Analysis

| Dimension | Assessment |
| :--- | :--- |
| **Does it extend the actual problem statement?** | Yes — it's the SQL router handling a class of question it currently can't, which is the stated core contribution of the project. |
| **Does it introduce new risk?** | Yes, two kinds: (1) a second place LLM output could get treated as executable if the validation step in 3.3 is skipped, and (2) group-by phrasing is a new potential path to individual-row leakage if synthesis is ever given raw rows instead of aggregates (3.5 prevents this by design — don't relax it later). |
| **Is it demo-able in a reasonable amount of time?** | **[Likely]** yes, scoped to two-way comparisons on 2–3 known columns. Full multi-hop arbitrary reasoning would not be. |
| **Does it need item 1 (golden dataset) first?** | Yes, non-negotiable. Without it you cannot tell a correct decomposition from a plausible-sounding wrong one, which defeats the purpose of building this at all. |
| **Priority relative to Kubernetes/HPA** | Higher. This strengthens the core claim; the K8s item didn't address the actual bottleneck and was correctly deprioritized. |

---

## 6. Order of Implementation

1. Finish the golden dataset and exact-match harness for the existing single-aggregate router (already planned separately).
2. Add the five comparison-category rows in section 4 to that same golden dataset, with ground truth computed independently (pandas on the mock data, not the app itself).
3. Build `is_comparison_query()` and the planner prompt (3.1–3.2).
4. Build `validate_plan()` with the allowlist (3.3) — do not skip this to "get a demo working faster."
5. Build the fixed-template executor (3.4).
6. Build synthesis and the trust-layer check (3.5–3.6).
7. Wire into `answer_query()` behind the existing scope check (3.7).
8. Run the full golden dataset, including the refusal cases, and only report an accuracy number once refusals behave correctly.

---

## 7. Definition of Done

- [ ] `is_comparison_query()` correctly separates comparison questions from single-aggregate ones on the golden set.
- [ ] Every plan is validated against an allowlist before execution; no plan field reaches SQL as raw string interpolation except through the fixed template set.
- [ ] Both sub-queries run on a `query_only` connection with parameterized values.
- [ ] Synthesis receives only the two aggregated numbers, never raw student rows.
- [ ] Trust layer flags synthesis sentences that don't match the given numbers.
- [ ] Comparison queries are unreachable on the student scope; only the placement/developer full-scope path can trigger this.
- [ ] Golden dataset comparison-category questions, including the three refusal cases, all behave as expected before any accuracy number is reported publicly.
