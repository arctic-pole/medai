# Contributing to MEDAI

`medai_spec.yaml` is the authoritative specification for this project. Read it, and
`IMPLEMENTATION_PLAN.md`, before making changes. Architecture must not change without
the user's explicit "CHANGE SPECIFICATION" authorization.

## Branches

- `main` — always deployable, never known-broken code.
- `develop` — integration branch.
- `feature/*` — one feature per branch.

## Commits

Prefix every commit subject with one of: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`.

## Before opening a PR

Per `medai_spec.yaml` `git.feature_requirements`, a feature must be:
1. Mapped to a specific requirement in `medai_spec.yaml` or `IMPLEMENTATION_PLAN.md`.
2. Implemented.
3. Tested (unit/integration/e2e/safety-adversarial as applicable).
4. Documented (the relevant file(s) under `docs/`).
5. Committed with a clear message.

## Task report format

Per `medai_spec.yaml` `agent_rules.task_loop.report_format`, report completed work as:

```
TASK / PHASE / CHANGES / TESTS / RESULT: PASS|FAIL|BLOCKED / LIMITATIONS / NEXT
```
