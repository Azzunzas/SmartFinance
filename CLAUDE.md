# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

SmartFinance is a single-user personal finance dashboard: bank data comes from the Pluggy API (Open Finance), is copied into Postgres, and is cross-checked as planned × actual spending. Being single-user is a deliberate scope decision: don't add caches, queues or extra services without a measured bottleneck.

Further reading: `docs/regras-do-projeto.md` (domain rules, conventions, roadmap), `docs/arquitetura-app-financas.md` (data model, endpoint contract), `DESIGN.md` (read before front-end work; visual rules and per-screen content).

## Commands

Backend (Python 3.14, run from the repo root). Only `tests/conftest.py` loads `.env`; everything else needs `DATABASE_URL` exported, because `core/database.py` reads it at import time.

```bash
docker start smartfinance-postgres
alembic upgrade head
uvicorn api.main:app --reload --port 8000   # set COOKIE_SECURE=false on http://localhost, or login won't stick

pytest                                       # whole suite
pytest tests/core/analysis/test_recurrence.py::test_name
ruff check . && ruff format .
mypy .

python -m jobs.sync <pluggy_item_id> [--kind FULL|INCREMENTAL]
python -m jobs.analysis
python -m jobs.check_consent
```

Dependencies are declared in `pyproject.toml`; the Docker images install from `requirements.lock` (`requirements-dev.lock` adds dev tools), so keep the lockfiles in step.

Front end (from `web/`):

```bash
npm start                                    # ng serve, proxies /api to localhost:8000
npm run build
npm test                                     # Vitest via ng test
npx ng test --include src/app/shared/modal/modal.directive.spec.ts
npm run generate:api                         # needs DATABASE_URL exported (imports api.main)
```

Without any user registered, create one with `POST /api/auth/register` (works only once).

## Test database

`pytest` **drops and recreates** the test database on every run, then applies all migrations, so a broken migration fails the suite. The target is `DATABASE_URL_TEST`, or else `DATABASE_URL` with `_test` appended; the suite refuses to run if the two match. The Postgres role must be allowed to create databases.

Tests use real Postgres, never database mocks. The `db_session` fixture wraps each test in a rolled-back transaction. The router `client` fixture (`tests/api/routers/conftest.py`) overrides `require_auth`; only `test_auth.py` exercises real auth.

## Architecture

```
Pluggy → jobs/pluggy → jobs/sync/mapping → core/ingestion (normalize) → core/repository (upsert)
                                                                             ↓
                                         jobs/analysis/run.py (classify, transfers, MV, recurrence, matching)
                                                                             ↓
                              api/routers → core/repository → web/ (Angular, via generated client)
```

- **`core/`** holds all domain logic. `core/analysis` works on plain dataclasses, and `core/repository` is the database layer. **`api/`** has no business rules, and SQLAlchemy models don't leak past the Pydantic schemas in `api/schemas`.
- **The dashboard never calls Pluggy per request.** Pluggy is a source, and Postgres is the permanent archive (Pluggy only serves 12 months).
- **`run_analysis` is deliberately non-incremental:** it reprocesses every transaction and must stay idempotent. Don't add change tracking.
- **Transaction boundaries belong to the caller.** `sync_item` and `run_analysis` don't commit; `api/deps.py:get_session` commits per request; jobs commit in their entry points.

### Manual vs automatic classification

Each contested field in `transaction_classification` has three columns (migration 0013): `<field>_auto` (written only by `run_analysis`), `<field>_manual` (written only by the user; NULL means "no opinion", which differs from False), and `<field>`, generated as `COALESCE(manual, auto)`, which is read-only. `note` and `exclude_from_analysis` are user-only. The sync never touches this table.

### What counts as real spending

The predicate is POSTED, account included in analysis, not an internal transfer, not a card payment, not manually excluded. It is repeated in `mv_monthly_cashflow`, `core/repository/analysis.py` and `core/repository/metrics.py`, so change all of them together. Card credits (`transaction.is_card_credit`, set at ingestion) are subtracted from `total_out` in the view and left out of the matchable pool used by planned items and recurrence detection.

Renaming a column does not break a materialized view: Postgres silently repoints it at the new name. A migration that changes columns the view reads must drop and recreate it, as 0013 does, or the view keeps reading the wrong data with no error.

### Sync and concurrency

- `core/locks.py` uses a Postgres advisory lock shared by the CronJob and the API across processes. It must be released explicitly, since closing the SQLAlchemy connection returns it to the pool still holding the lock.
- **CronJob path** (`jobs/sync/__main__.py`): one CronJob per bank connection at 06:00, syncing a single item, with analysis as a separate CronJob at 06:30. Adding a bank means a new block in `deploy/k8s/sync-cronjob.yaml` plus a secret key.
- **Manual path** (`jobs/sync/manual.py`, from `POST /api/sync/run`): acquires the lock, returns 202, and a `BackgroundTask` syncs all active connections, runs analysis and releases the lock. It uses its own sessions, with one transaction per connection.
- `kind="FULL"` ignores the cursor. Any other value is incremental, so `MANUAL` is only an origin label.
- Incremental sync makes two passes: `createdAtFrom` since the cursor, then a 45-day re-read by date. Pluggy's `createdAtFrom` never returns older records, so the re-read is the only way status changes (PENDING → POSTED) arrive.
- A rollback also removes the FAILED `sync_run`, so failure paths re-record it in a fresh session. Pass stored error text through `core/redaction.py`.

### Front end

Standalone components and signals with no new `NgModule`; lazy routes per feature under `web/src/app/features`; Reactive Forms in the budget module.

`web/src/app/core/api/generated` and `web/openapi.json` are generated by Orval. Never edit them or hand-write response interfaces; run `npm run generate:api` after changing the API.

Never show fictional data: when no API or calculation exists, use an explicit empty state (see `DESIGN.md`).

## Domain rules

These decide whether the numbers are true; the full list is in `docs/regras-do-projeto.md` §2.

1. Card purchases belong to the month of purchase (`accrual_date`), not of the bill.
2. Bill payments (`is_card_payment`) are not expenses.
3. Transfers between own accounts are not expenses; they are detected by equal and opposite amounts within ±2 days between `is_own = true` accounts.
4. `PENDING` never counts as spent, only as a future commitment.
5. Never `DELETE` from `transaction`.
6. Ingestion is idempotent: dedup by `pluggy_transaction_id` **and** `fingerprint`, because a reconnection issues new IDs for the same transactions.
7. Capture `balance_snapshot` on every sync; Pluggy has no balance history.
8. Sign is normalized once at ingestion into `direction` and `amount_abs`. No `CASE WHEN account.type` in queries.
9. Filter investments by `is_active` by default.
10. A credit on a card account (`is_card_credit`: refund, "pula compra", cashback) is never income: it reduces `total_out` in the month it posts. Category totals are not reduced.

## Conventions

- Commits follow Conventional Commits, in Portuguese. Code comments and docs are in Portuguese too.
- Migrations are linear with no branches, and every schema change goes through one. Numbered files live in `alembic/versions`.
- SQLAlchemy 2.0 `select()` style only; mypy strict; ruff at line length 100.
- Logs and stored error messages contain no identifiable financial data.
- Required test coverage: sync dedup, internal transfer detection, recurrence detection, budget rule matching.
