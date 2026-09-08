# Pulse Platform

A multi-tenant API platform built on one persisted, per-user persona model.
Successor to the [pulse-agent](https://github.com/HenryMorganDibie/pulse-agent)
hackathon project — see [CONTRACTS.md](./CONTRACTS.md) for exactly what was
ported unchanged, what was adapted, and what was deliberately dropped in the
rebuild.

## Two products, one persona core

1. **Simulate** (flagship) — given a subject's interaction history and an
   unseen item, predict the rating and review they'd write, in their own
   tone. Built for product/UX/marketing teams doing synthetic user testing
   before shipping something, instead of spending real research budget on it.
2. **Recommend** — given a subject and an optional query/conversation, return
   ranked recommendations from the tenant's own catalog, backed by real
   pgvector semantic search over that catalog blended with the subject's
   category preferences.

Both read from the same tenant-scoped, persisted `UserState` (behavioural +
textual + contextual profile), computed once per subject and cached — not
rebuilt on every request.

## Setup

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# fill in GROQ_API_KEY, HF_API_KEY, and DATABASE_URL
```

### 3. Run the database + API

```bash
docker-compose up --build
```

This brings up Postgres with pgvector (migrations in `migrations/` run
automatically on first boot) and the API at `http://localhost:8000/docs`.

To point at a hosted Supabase project instead of the local `db` service, set
`DATABASE_URL` in `.env` to your project's pooled connection string, run
`migrations/001_init.sql` against it once, and run only the `api` service.

### 4. Provision a tenant

There is no public tenant-registration endpoint — onboarding mints a
credential with full access to that tenant's data, which belongs behind
operator access to the database, not an open HTTP route.

```bash
python scripts/create_tenant.py "Acme Corp"
```

Prints an API key exactly once — store it now. To revoke a key later:

```bash
python scripts/revoke_api_key.py <key_prefix>
```

## API

All `/v1/*` routes require `Authorization: Bearer <api_key>`.

### Record a subject's history

```
POST /v1/subjects/{external_id}/reviews
{
  "item_id": "i_042",
  "category": "Food",
  "rating": 4.0,
  "text": "Great spot, very consistent.",
  "timestamp": "2026-08-01T12:00:00Z"
}
```

### Simulate — `POST /v1/simulate-review`

**Request**
```json
{
  "subject_external_id": "u_001",
  "item": {
    "item_id": "i_199",
    "name": "The Grill House",
    "category": "Food",
    "description": "American grill, mid-range, casual",
    "attributes": { "cuisine": "American", "price_range": "$$" }
  }
}
```

**Response**
```json
{
  "simulated_rating": 4.5,
  "simulated_review": "Honestly one of the better spots I've been to in a while.",
  "confidence": 0.87,
  "decision_factors": [
    "Has a history of rating Food items (80% of past reviews)",
    "Review generated in their established tone: expressive"
  ]
}
```

`decision_factors` is deterministic, derived directly from the subject's
persona profile — never raw model chain-of-thought or internal error text.
See `CONTRACTS.md` for why this replaced `pulse-agent`'s `reasoning_trace`.

### Upload a catalog — `POST /v1/catalog/items`

```json
{
  "items": [
    { "item_id": "i_305", "name": "The Rooftop Lounge", "category": "Nightlife",
      "attributes": { "price_range": "$$", "vibe": "chill" } }
  ]
}
```

Each item is embedded server-side (`sentence-transformers/all-MiniLM-L6-v2`)
and stored with the embedding model name, so a future model change is a
detectable condition, not a silent mismatch in the same similarity index.

### Recommend — `POST /v1/recommend`

**Request**
```json
{
  "subject_external_id": "u_042",
  "query": "something chill for the weekend, not too expensive"
}
```

**Response**
```json
{
  "recommendations": [
    {
      "rank": 1, "item_id": "i_305", "name": "The Rooftop Lounge",
      "category": "Nightlife", "predicted_rating": 4.3,
      "explanation": "Matches casual, mid-range weekend spots.",
      "ndcg_score": 0.91
    }
  ],
  "inferred_intent": "relaxed weekend outing, budget-conscious",
  "cold_start": false,
  "decision_factors": ["Ranked using their preference history, especially: Nightlife, Food"]
}
```

## Project structure

```
pulse-platform/
├── src/
│   ├── core/            # config, db pool, API-key auth
│   ├── persona/          # shared persona core — models, pipelines, cache, Groq client
│   ├── products/
│   │   ├── simulate/     # Product A
│   │   └── recommend/    # Product B — reasoning, ranking, pgvector retrieval, embeddings
│   ├── schemas/api.py    # public request/response models
│   └── main.py
├── migrations/           # SQL — tenants, api_keys, subjects, review_records,
│                          #   user_states, catalog_items (pgvector), request_log
├── scripts/               # admin tenant/key provisioning (not HTTP endpoints)
└── tests/
```

## Testing

```bash
pytest tests/ -v
```

Current coverage: persona pipeline arithmetic (behavioural, contextual),
decision-factor derivation (both products, including a check that no
exception/fallback text leaks into the customer-facing response), and API-key
hashing. LLM-calling code paths (textual pipeline, simulate agent, ranking)
need a live `GROQ_API_KEY` and aren't covered by these unit tests yet.

## Explicitly out of scope for this pass

Billing/metering beyond the `request_log` audit table, a tenant self-serve
dashboard, a second LLM provider tier, an embeddable widget frontend, and an
evaluation harness validated against real usage (the ported NDCG@k is
self-referential — see CONTRACTS.md). Noted so they're not silently dropped.
