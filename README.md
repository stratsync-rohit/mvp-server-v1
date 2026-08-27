# MVP v1 (expandable)

Backend for the Microsoft Teams notification integration system.

FastAPI owns **clients**, **Teams channel integrations**, and **MongoDB
storage**. It never talks to Microsoft Teams, Microsoft Graph, or the Bot
Framework directly. All actual notification delivery is delegated to the
existing **n8n** workflow, which builds the Adaptive Card and posts it to
the client's stored Teams webhook.

```text
Frontend
   ↓
FastAPI Backend  (clients, channels, Mongo, resolves webhook, triggers n8n)
   ↓
MongoDB
   ↓
FastAPI triggers n8n webhook (POST N8N_NOTIFICATION_WEBHOOK_URL)
   ↓
n8n builds the Teams Adaptive Card
   ↓
n8n sends the notification to the client's stored Teams webhook
   ↓
Specific Microsoft Teams Channel
```

---

## 1. Project Structure

```text
backend/
├── app/
│   ├── main.py                  # FastAPI app, lifespan, CORS, exception handlers
│   ├── config.py                # Settings (env vars)
│   ├── database.py              # Motor client, index creation
│   ├── dependencies.py          # DI wiring (repositories/services)
│   ├── exceptions.py            # Domain exceptions -> HTTP status codes
│   │
│   ├── api/
│   │   ├── clients.py           # /api/clients*
│   │   ├── teams_channels.py    # /api/clients/{id}/teams/channels, /api/teams/channels/*
│   │   └── notifications.py     # /api/notifications/trigger
│   │
│   ├── schemas/
│   │   ├── common.py            # PyObjectId, APIResponse envelope
│   │   ├── client.py            # ClientCreate / ClientUpdate / ClientResponse
│   │   ├── teams_channel.py     # TeamsChannelCreate / Update / Response
│   │   └── notification.py      # NotificationTriggerRequest / Response
│   │
│   ├── repositories/
│   │   ├── client_repository.py
│   │   └── teams_channel_repository.py
│   │
│   ├── services/
│   │   ├── client_service.py
│   │   ├── teams_channel_service.py
│   │   ├── notification_service.py
│   │   └── n8n_service.py       # httpx client that POSTs to n8n
│   │
│   └── utils/
│       ├── teams_url_parser.py  # Parses Teams "copy channel link" URLs
│       └── webhook_masking.py   # Never expose full webhook URLs
│
├── tests/                       # pytest + httpx ASGI client + mongomock-motor
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .gitignore
├── .env.example
├── pytest.ini
└── README.md
```

**Layering rule:** API routers only parse/validate HTTP input and call a
service. Services hold business rules (duplicate checks, active/inactive
checks, orchestration). Repositories are the only code that touches
MongoDB directly. `n8n_service.py` is the only code that makes outbound
HTTP calls to n8n. Nothing in this codebase calls Microsoft Teams,
Microsoft Graph, or the Bot Framework.

---

## 2. Quick Start

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- MongoDB: localhost:27017 (persisted in the `mongo_data` named volume)

Edit `.env` and point `N8N_NOTIFICATION_WEBHOOK_URL` at your real n8n
instance before triggering real notifications. No n8n container is created
by this compose file — an existing n8n instance is assumed.

After changing `.env`, recreate the backend so Docker loads the new values:

```bash
docker compose up -d --force-recreate backend
docker compose exec backend env | grep '^N8N_'
```

If application code or dependencies are not bind-mounted in your deployment,
rebuild instead with `docker compose up -d --build backend`.

### Running tests locally (without Docker)

```bash
pip install -r requirements.txt --break-system-packages   # or use a venv
pytest -v
```

Tests use `mongomock-motor` (no real MongoDB needed) and mock the n8n HTTP
call, so **no test ever sends a real Teams notification**.

---

## 3. Environment Variables

| Variable | Purpose |
|---|---|
| `APP_NAME` | Display name used in Swagger |
| `APP_ENV` | `development` or `production`. In production, Teams webhook URLs must be HTTPS |
| `HOST` / `PORT` | Uvicorn bind address |
| `MONGODB_URI` | Mongo connection string |
| `MONGODB_DATABASE` | Database name |
| `N8N_NOTIFICATION_WEBHOOK_URL` | **System-level**, single n8n webhook URL. NOT stored per client |
| `N8N_REQUEST_TIMEOUT_SECONDS` | Timeout for the FastAPI → n8n HTTP call |
| `CORS_ORIGINS` | Comma-separated list of allowed frontend origins |

---

## 4. MongoDB Design

### `clients`

```json
{
  "_id": "ObjectId('665f1...')",
  "name": "ABC Shipping",
  "code": "ABC-001",
  "is_active": true,
  "created_at": "2026-08-20T09:12:03Z",
  "updated_at": "2026-08-20T09:12:03Z"
}
```

Index: `{ "code": 1 }` — **unique**.

### `teams_channels`

```json
{
  "_id": "ObjectId('665f2...')",
  "client_id": "ObjectId('665f1...')",
  "team_name": "Operations Team",
  "channel_name": "Risk Alerts",
  "channel_url": "https://teams.microsoft.com/l/channel/19%3aabc...%40thread.tacv2/Risk%20Alerts?groupId=c893...&tenantId=7f30...",
  "teams_webhook_url": "https://prod-01.westus.logic.azure.com:443/workflows/xxxx",
  "tenant_id": "7f301234-...",
  "team_id": "c8931234-...",
  "channel_id": "19:abc123@thread.tacv2",
  "is_active": true,
  "created_at": "2026-08-20T09:15:40Z",
  "updated_at": "2026-08-20T09:15:40Z"
}
```

Indexes:

- `{ "client_id": 1 }` — fast lookup of a client's channels.
- `{ "teams_webhook_url": 1, "is_active": 1 }` — duplicate-webhook prevention.
- `{ "client_id": 1, "tenant_id": 1, "team_id": 1, "channel_id": 1, "is_active": 1 }`
  — duplicate-destination prevention (only enforced when the Teams URL was
  successfully parsed for all three identifiers).

`teams_webhook_url` is a **secret**: it is stored in Mongo, never logged,
never included in exception messages, and never returned by any
frontend-facing GET/POST/PUT response. Public responses only ever include
`"webhook_configured": true|false`.

---

## 5. API Reference

All list/create/read/update responses use the envelope:

```json
{ "success": true, "message": "optional", "data": { ... } }
```

### Health

```http
GET /health
```

```json
{ "status": "ok" }
```

### Clients

| Method | Path | Notes |
|---|---|---|
| POST | `/api/clients` | `{ "name", "code" }`. 409 on duplicate `code`. |
| GET | `/api/clients` | Returns active clients only. |
| GET | `/api/clients/{client_id}` | 404 if not found. |
| PUT | `/api/clients/{client_id}` | All fields optional. |
| DELETE | `/api/clients/{client_id}` | Soft delete (`is_active = false`). |

### Teams Channels

| Method | Path | Notes |
|---|---|---|
| POST | `/api/clients/{client_id}/teams/channels` | Parses `channel_url`, stores webhook, 409 on duplicate webhook or duplicate destination. |
| GET | `/api/clients/{client_id}/teams/channels` | List a client's channels (webhook never included). |
| GET | `/api/teams/channels/{integration_id}` | Single channel, webhook never included. |
| PUT | `/api/teams/channels/{integration_id}` | All fields optional; omitted `teams_webhook_url` preserves the existing one. Re-parses `channel_url` if changed. |
| DELETE | `/api/teams/channels/{integration_id}` | Soft delete. |
| POST | `/api/teams/channels/{integration_id}/test` | Sends an `integration_test` event through n8n — never posts to Teams directly from FastAPI. |

### Notifications

```http
POST /api/notifications/trigger
```

```json
{
  "risk_id": "RSK-21132-0472",
  "destination_id": "TEAMS_CHANNEL_INTEGRATION_ID"
}
```

Resolves the channel, client, complete risk and private webhook from MongoDB,
validates that all are active, then POSTs to
`N8N_NOTIFICATION_WEBHOOK_URL`.

---

## 6. Example Requests

```bash
# Create a client
curl -X POST http://localhost:8000/api/clients \
  -H "Content-Type: application/json" \
  -d '{ "name": "ABC Shipping", "code": "ABC-001" }'

# Add a Teams channel integration
curl -X POST http://localhost:8000/api/clients/CLIENT_ID/teams/channels \
  -H "Content-Type: application/json" \
  -d '{
    "team_name": "Operations Team",
    "channel_url": "PASTE_TEAMS_COPY_LINK",
    "teams_webhook_url": "PASTE_TEAMS_WEBHOOK"
  }'

# List a client's channels
curl http://localhost:8000/api/clients/CLIENT_ID/teams/channels

# Trigger a notification
curl -X POST http://localhost:8000/api/notifications/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "risk_id": "RSK-21132-0472",
    "destination_id": "CHANNEL_INTEGRATION_ID"
  }'

# Send a test notification for a channel integration
curl -X POST http://localhost:8000/api/teams/channels/CHANNEL_INTEGRATION_ID/test
```

---

## 7. FastAPI → n8n → Teams Flow

**Setup flow:**

```text
CEO/Admin → Frontend → Create Client → Add Teams Channel → FastAPI
   → MongoDB stores: client, channel info, Teams webhook
```

**Notification flow:**

```text
Frontend / Application
   ↓ POST /api/notifications/trigger
FastAPI
   ↓ resolve selected Teams destination and owning client
   ↓ resolve complete risk by risk_id
   ↓ validate client, destination and risk are active
   ↓ read secret teams_webhook_url internally
   ↓ POST to N8N_NOTIFICATION_WEBHOOK_URL
n8n
   ↓ build Adaptive Card from the resolved risk
   ↓ Teams branch
   ↓ dynamic Teams webhook URL (from payload, not hard-coded)
   ↓ selected Microsoft Teams Channel
```

Payload FastAPI sends to n8n:

```json
{
  "risk": {
    "risk_id": "RSK-21132-0472",
    "title": "Supplier Reliability Risk Detected",
    "industry": "Distribution & Trading"
  },
  "destination": "teams",
  "client": { "id": "665f1...", "code": "ABC-001", "name": "ABC Shipping" },
  "teams_channel": {
    "destination_id": "665f2...",
    "team_name": "Operations Team",
    "channel_name": "Risk Alerts",
    "tenant_id": "7f301234-...",
    "team_id": "c8931234-...",
    "channel_id": "19:abc123@thread.tacv2"
  },
  "teams_webhook_url": "https://prod-01.westus.logic.azure.com:443/workflows/xxxx"
}
```

`teams_webhook_url` is included here intentionally — this is an
internal, service-to-service call. It is never returned by any API that
faces the frontend.

---

## 8. Changes Required in the Existing n8n Workflow

The current workflow's Teams **HTTP Request** node presumably has a
**hard-coded** Teams webhook URL (or one webhook per workflow branch). To
support per-client, per-channel routing, make these changes in n8n:

1. **Webhook trigger node** (`POST /webhook/rrm-alert-click`): no changes
   needed to the trigger itself — it already accepts a JSON body. FastAPI
   now sends a richer payload (see above) alongside the existing
   `card_id` / `destination` fields, so the same webhook node keeps
   working.
2. **Teams HTTP Request node**: change the URL field from a static string
   to an expression that reads the webhook from the incoming payload:
   ```text
   {{$json.teams_webhook_url}}
   ```
   (or `{{$json.body.teams_webhook_url}}` depending on how n8n normalizes
   the webhook body in your version).
3. **Card-building node(s)**: no change to card-building logic — `card_id`
   is passed exactly as before (`owner-funding-short`,
   `dry-dock-budget`, `revenue-to-cover`, `supplier-reliability`, etc.).
   Optionally, the new `teams_channel.team_name` / `channel_name` fields
   can be used to personalize the card title/subtitle if desired.
4. **Integration test branch** (new, optional): if you want a distinct
   card for `event_type == "integration_test"` payloads sent by
   `POST /api/teams/channels/{id}/test`, add an `IF` node checking
   `$json.event_type === "integration_test"` before the card-building
   step, and route it to a simple "Test successful ✅" Adaptive Card.
5. **No FastAPI-side changes are needed in n8n's webhook path, auth, or
   trigger URL** — only the destination URL used by the Teams HTTP
   Request node needs to become dynamic.

---

## 9. Security Notes

- `teams_webhook_url` is stored in MongoDB, read only inside
  `notification_service.py` / when building the n8n payload, and is never
  logged, never included in exception messages, and never serialized in
  any API response (`TeamsChannelResponse` only has `webhook_configured:
  bool`).
- In `APP_ENV=production`, adding or updating a Teams channel requires
  `teams_webhook_url` to start with `https://`.
- Duplicate active webhook URLs, and duplicate active
  client/tenant/team/channel combinations, are rejected with `409
  Conflict` — and the conflict response never echoes the webhook URL.

---

## 10. Design Notes / Assumptions

- The n8n payload includes both the client's Mongo ID and human-readable code.
- Teams channel URL parsing is best-effort: unparseable URLs still allow
  the integration to be created (`channel_name`/`tenant_id`/`team_id`/
  `channel_id` stored as `null`), because the Teams **webhook URL**, not
  the parsed metadata, is what actually delivers the notification.
- The public trigger accepts only `risk_id` and `destination_id`; Teams is the
  only delivery destination in this MVP.
