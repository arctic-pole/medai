# MEDAI — Evaluation

> Phase 14 (Evaluation). New this phase — `medai_spec.yaml`'s `testing:` and
> `evaluation_dataset`/`evaluation_metrics` sections had no dedicated doc before now.

## Scope and the two open decisions this phase started with

The implementation plan flagged two decisions as needing the user's own input, not to be
invented by the agent:

1. **Whether to attempt real Gemini calls for generation-quality metrics**, given this
   session's well-documented history of Gemini free-tier quota/latency problems (see
   `docs/KNOWN_LIMITATIONS.md`, Phase 8 onward). User's choice: **attempt them anyway**,
   accepting the risk.
2. **How to handle safety-metric acceptance thresholds**, which the plan explicitly warns
   need real clinical input and must never be invented. User's choice: **report actual
   numbers, gate only on zero-tolerance items** — a case that should trigger a deterministic
   emergency/contraindication rule and doesn't is a hard test failure; graded probabilistic
   thresholds (e.g. "95% sensitivity") are left unset rather than invented.

## `testing.unit` / `testing.integration` / `testing.safety_adversarial` / `testing.end_to_end`

These four spec categories were already substantially covered by prior phases' test files
(auth, patient state, safety engine, medication safety, output validator, access control,
prompt injection — see each phase's entry in `docs/KNOWN_LIMITATIONS.md`). This phase closed
the two categories with no dedicated coverage yet:

- **`testing.safety_adversarial`** — `backend/tests/unit/test_safety_adversarial_suite.py`.
  The module docstring maps all 10 spec-listed adversarial categories to either an existing
  test elsewhere (named by file) or a new test in this file. New coverage: contradictory vitals
  are both kept in `measurements` (not silently resolved — the current `vitals` snapshot
  reflects the newest reading, but the full history survives for audit); a contradictory
  `Assessment.status`/`escalation` pair is caught by `app.validation.checks.check_contradictions`;
  malformed structured LLM output fails closed to `SAFE_FALLBACK`, not a crash; a "hallucinating"
  Assessment (claims with no backing evidence) is corrected and, when correction still fails,
  falls back to `SAFE_FALLBACK` rather than releasing an ungrounded claim; and — the check in
  the other direction — a genuinely hedged, low-confidence "I don't know enough" response with
  no evidence to cite is *not* rejected for lacking evidence, since penalizing honest
  uncertainty would push the model toward fabricating citations instead.
- **`testing.end_to_end`** — `backend/tests/integration/test_e2e_conversation.py`. One test,
  walking a genuinely fresh patient (no profile/history/allergies/medications at all) through
  every real follow-up question the conversation manager asks, entirely over HTTP, in the exact
  order `conversation_manager.question_priority` defines, until `POST /messages` itself runs
  the full real pipeline and returns a validated `Assessment` — the single-conversation version
  of what earlier phases' tests already proved in pieces.

## `evaluation_dataset`

`backend/evaluation/dataset.py` — one `EvaluationCase` per spec `case_types` value (`normal`,
`ambiguous`, `incomplete`, `contradictory`, `emergency`, `medication_conflict`,
`insufficient_information`), built to the spec's own field schema. The spec's rule is verbatim:
"Do not create expected answers from model guesses; use validated reference material." Every
case whose `expected_safety_state` is anything other than the deterministic-nothing-triggers
default (`PASS`) is grounded in a source already cited elsewhere in this codebase:

| case_id | expected_safety_state | source |
|---|---|---|
| `contradictory-001` | `MODIFY` | AHA/ACC tachycardia threshold (`app/safety/vital_rules.py`) |
| `emergency-001` | `ESCALATE` | WHO pulse-oximetry manual, SpO2 emergency threshold |
| `medication_conflict-001` | `BLOCK` | openFDA label match against a recorded allergy |

`backend/tests/integration/test_evaluation_dataset.py` (11 tests) is the harness: it seeds each
case via real API calls (plus a direct `Symptom` DB insert, since no CRUD endpoint exists for
symptoms — the same pattern `test_assessment.py` already established), then calls the real
deterministic pipeline pieces directly (`build_patient_state`, `evaluate_safety`,
`check_candidate_medication` for the medication-conflict case) — never fakes standing in for
these specific pieces, since they're what the metrics below actually measure.

**A real bug in this dataset's own construction was found and fixed via the tests
themselves**, twice:

- `ambiguous-001` was missing a `medications` entry (empty list, no field in
  `expected_information_requirements` to match), which produced an unexpected extra "missing
  field" in `test_case_missing_info_matches_expected_information_requirements`. Fixed by adding
  `medications=[{"name": "none"}]`.
- The same root cause was later found again, live, on 4 more cases (`normal-001`,
  `contradictory-001`, `emergency-001`, `medication_conflict-001`) while running
  `live_generation_check.py` (below) — see that section for the full account. Fixed the same
  way.

## `evaluation_metrics.safety` — real numbers

Computed and printed by `test_safety_metrics_summary_meets_zero_tolerance_gates`, run against
this 7-case dataset:

```
emergency_detection_sensitivity: 1.0 (1/1)
contraindication_detection: 1.0 (1/1)
unsafe_recommendation_rate: 0/7
```

**What these numbers do and don't mean**: they confirm this specific, sourced, 7-case dataset
has zero misses — not a clinically validated sensitivity/specificity claim. With only one
`ESCALATE` case and one `BLOCK` case in the dataset, "1.0 (1/1)" is a single data point, not a
statistically meaningful rate. A larger, clinically-reviewed dataset with a real graded
threshold is future work this phase deliberately did not invent a number for (see "the two open
decisions" above).

Only the zero-tolerance gates are hard-asserted in the test (an under-escalation on any case is
a test failure); nothing here is a soft/advisory metric that could silently regress.

## `evaluation_metrics.generation` — attempted live, not obtained

Per the user's explicit choice to attempt real Gemini calls, `backend/evaluation/
live_generation_check.py` was built and run against the real dev database with no provider
overrides — real `GeminiProvider`, real local `sentence-transformers` embeddings — driving all
7 dataset cases through the actual `POST /messages` endpoint end-to-end, exactly the code path
a real user's phone would hit.

**Result: the same Gemini free-tier wall documented since Phase 8 (20 requests/day, shared
across model ids, not a clean per-model bucket) was hit again, this time before a single case
reached real assessment generation.** `evidence_grounded_response_rate`, `unsupported_claim_rate`,
and `schema_compliance` could not be measured with real model output this session.

While diagnosing why the quota exhausted so quickly, a real, separate bug surfaced: 4 of the 7
dataset cases (`normal-001`, `contradictory-001`, `emergency-001`, `medication_conflict-001`)
had an empty `medications=[]` with no corresponding `current_medications` entry in
`expected_information_requirements`. An empty list and "not yet answered" look identical to the
conversation manager, so it correctly, endlessly re-asked the same medications question on
every one of those cases — and the script's own generic "I don't have anything else to add"
follow-up reply can never resolve a structured-data gap like that. This burned the day's entire
request budget on repeated question-phrasing calls for one field, on one case, before the
script could even reach a case's final assessment-generation call.

Two fixes were made, both disclosed as genuine findings rather than silently patched:

1. **The dataset itself** — populated `medications=[{"name": "none"}]` on all 4 affected cases,
   matching the same fix already applied to `ambiguous-001` earlier in this phase for the
   identical root cause. This makes the dataset internally consistent: a case only omits a
   field from `expected_information_requirements` if that field is actually going to be
   populated during setup.
2. **The script** — `live_generation_check.py` now bails out of a case's follow-up loop as soon
   as the manager asks the identical question twice in a row, rather than retrying up to 5
   times blindly. A generic reply can never resolve a structured-data gap, so retrying past the
   first repeat only burns quota with no chance of a different outcome.

The script is otherwise complete: for any case that *does* reach `is_assessment: true`, it
records the real Gemini output, whether it passed `get_validated_output`'s checks on the first
attempt (`schema_compliance_rate`), and writes both a console summary and
`backend/evaluation/results.json`. It has not yet been re-run to completion — the day's quota
was already spent by the run described above. Re-running it (`python -m
evaluation.live_generation_check`, from `backend/`, once the quota resets or a paid tier is
configured) is the concrete next step to obtain real `evaluation_metrics.generation` numbers;
this file should be updated with the real results once that happens.

## Standing limitations

- 7 cases is a hand-built minimum-viable dataset covering each spec `case_type` once, not a
  statistically powered benchmark. Expanding it is future work.
- `evaluation_metrics.retrieval`/`extraction` (spec-named metric groups) are not separately
  measured — Phase 5/6's own live verification already covers retrieval relevance and
  extraction correctness qualitatively (see their entries in `docs/KNOWN_LIMITATIONS.md`); no
  dedicated automated metric was built for them this phase.
- `live_generation_check.py` writes real rows to the dev database under `eval-<case_id>
  @example.com` accounts and does not clean them up — acceptable for a personal dev database,
  not something to point at a shared or production database.
