# MEDAI — API

Base URL (local dev): `http://localhost:8000`. All endpoints (except `/healthz`, `/auth/*`)
require `Authorization: Bearer <access_token>`.

## Phase 2 endpoints (conversation)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/conversations` | bearer | Create a new conversation for the current patient |
| GET | `/conversations` | bearer | List the current patient's conversations |
| GET | `/conversations/{id}` | bearer | Get one conversation (404 if not owned by caller) |
| POST | `/messages` | bearer | `{conversation_id, content}` → stores the user message, returns `{user_message, assistant_message}` |
| GET | `/messages?conversation_id=` | bearer | List messages in a conversation (404 if not owned by caller) |

The assistant reply is a **Phase 2 scaffold only** (`app/conversation/stub_reply.py` — echoes the
user's text back with a placeholder note). No medical reasoning happens yet, per
`phases.2_conversation.constraint`; that starts in Phase 3+.

## Phase 1 endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/healthz` | none | Liveness check |
| POST | `/auth/register` | none | Create a user + patient record, returns token pair |
| POST | `/auth/login` | none | Returns token pair |
| POST | `/auth/refresh` | none (refresh token in body) | Returns a new access token |
| GET | `/patient` | bearer | Current patient's id/created_at |
| GET | `/profile` | bearer | Current patient's profile (auto-created on first read) |
| PATCH | `/profile` | bearer | Partial update of profile fields |
| GET/POST | `/history` | bearer | List / create medical history entries |
| PATCH/DELETE | `/history/{id}` | bearer | Update / delete one entry (404 if not owned by caller) |
| GET/POST | `/allergies` | bearer | List / create allergy entries |
| PATCH/DELETE | `/allergies/{id}` | bearer | Update / delete one entry (404 if not owned by caller) |
| GET/POST | `/medications` | bearer | List / create current-medication entries |
| PATCH/DELETE | `/medications/{id}` | bearer | Update / delete one entry (404 if not owned by caller) |

Every endpoint has a pydantic request/response schema (`app/schemas/`), requires authentication
except `/healthz` and `/auth/*`, validates input at the boundary, and returns structured error
responses (`{"detail": "..."}`) — per `api_endpoints.every_endpoint_requires`.

Interactive schema: `GET /docs` (Swagger UI) or `GET /openapi.json` when the server is running.

## Auth flow

1. `POST /auth/register {email, password}` → `{access_token, refresh_token}`
2. Use `access_token` as a Bearer token on subsequent requests (15 min default expiry).
3. `POST /auth/refresh {refresh_token}` → new `access_token` when the old one expires.

## Not yet implemented

`/symptoms`, `/vitals`, `/devices`, `/assessment`, `/evidence`, `/safety`, `/audit` (read API)
from `api_endpoints.groups` land in later phases per `IMPLEMENTATION_PLAN.md`.
