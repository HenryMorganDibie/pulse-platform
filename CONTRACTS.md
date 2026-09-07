# Contracts — what changed from pulse-agent, and why

This exists so a future behavioral difference can be traced to either "the
infrastructure migration changed how this runs" or "the logic was
intentionally changed" — not left ambiguous. Source: `HenryMorganDibie/pulse-agent`.

## Ported unchanged (same formulas, same prompts)

- **Behavioural pipeline arithmetic** (`src/persona/pipelines.py::_behavioural_pipeline`,
  from `persona_agent.py::_behavioural_pipeline`): avg/std rating, category
  affinity as a normalized count, recency-weighted average via `1/(i+1)`
  harmonic weights, `rating_bias = avg - 3.7` platform baseline, harsh/generous
  thresholds (`< 3.0` / `>= 4.3`). Not touched.
- **Textual pipeline prompt** (`_textual_pipeline`, from the same file):
  identical system/user prompt asking for `dominant_tone`,
  `avg_review_length`, `sentiment_polarity`, `vocabulary_richness`,
  `uses_first_person`, `common_phrases`. Same `ALLOWED_TONES` safety net
  (`safe_tone()` in `persona/models.py`, was `_safe_tone()` in the original).
- **Contextual pipeline logic** (`_contextual_pipeline`): identical cold-start
  (`len(history)==0`) and sparse (`<5`) thresholds, same cross-domain
  derivation (categories outside the top-2 by count), same recency-days calc.
- **Simulate's 3-step flow and prompts** (`products/simulate/agent.py`, from
  `review_agent.py`): rating-anchor formula (`anchor + bias*0.3`, clamped
  1.0-5.0), the rating/review/quality-score prompts, and the tone-instruction
  strings per `ToneProfile` (including the Nigerian-English variant) are
  unchanged.
- **Recommend's reasoning + ranking logic** (`products/recommend/reasoning.py`,
  `ranking.py`, from `reasoning_agent.py`/`ranking_agent.py`): cold-start /
  sparse / cross-domain strategy selection, intent-extraction prompt shape,
  LLM scoring prompt, dedup + top-k, and the NDCG@k formula are unchanged.
  **NDCG@k is still self-referential** — computed against the same LLM call's
  own `relevance_score`, not against real user behavior. That was true in the
  original and is still true here; it's an internal consistency check, not a
  quality metric, until there's real usage data to validate ranking against.
- **Fault-tolerance pattern**: every pipeline/step still fails independently
  and substitutes a named fallback rather than raising — this was one of the
  genuinely good decisions in the hackathon build.

## Adapted (same intent, different mechanism)

- **UserState is persisted and cached**, not rebuilt every request. New:
  `persona/store.py::get_or_build_user_state`. Pipelines now read
  `ReviewRecord`s from the `review_records` table (via `_fetch_history`)
  instead of a `review_history` list embedded in the request body.
- **Retrieval is real vector search, not keyword overlap.** The old
  `retrieval_tool.py` scored `keyword_overlap*0.35 + category_affinity*0.50 +
  price_affinity*0.15` against a global mock catalog. The new
  `products/recommend/retrieval.py` does pgvector cosine similarity (weight
  0.7) blended with category affinity (weight 0.3), scoped per tenant, over a
  tenant-uploaded catalog. Price-affinity scoring was dropped — it was a small
  hardcoded heuristic (`$$$ + generous_rater -> +0.15`) that doesn't
  generalize across arbitrary tenant catalogs with arbitrary attribute
  schemas; a tenant-configurable scoring weight is a reasonable future
  addition if a customer asks for it, not built speculatively now.
- **Reasoning trace is no longer returned to callers.** The old API exposed
  `reasoning_trace: List[str]` verbatim, including internal fallback/exception
  text (e.g. `"Fallback rating used: {exc}"`). That trace is now logged
  server-side only (`logger.info(...)` in each router) and the API instead
  returns `decision_factors: List[str]` — a short, deterministic list derived
  directly from the persona profile (category affinity, rater bias, tone,
  cold-start/strategy), never from LLM free text or exception messages. See
  `products/simulate/agent.py::_decision_factors` and
  `products/recommend/router.py::_decision_factors`.
- **One shared Groq client** (`persona/llm.py`) replaces 4 copy-pasted
  `_call_groq`/`_parse_json` implementations across the old agent files.
  Same retry-free, timeout-then-raise behavior; call sites are unchanged in
  spirit (system+user prompt in, string out, `GroqError` on failure).

## Deliberately discarded

- **LangGraph.** The old graph's only job was routing one `graph.ainvoke()`
  call to Task A or Task B after a shared Node 1 — the API's routing (two
  separate endpoints) now does that job directly, and dropping it makes the
  "skip persona construction if cached" short-circuit a plain `if`, not a
  conditional graph edge. See the architecture-decisions section of
  `~/.claude/plans/sorted-roaming-rose.md` for the full reasoning.
- **`embedding_tool.py` (dead code)** — was declared but never imported
  anywhere in pulse-agent. Its intent (sentence-transformers embeddings) is
  what `products/recommend/embeddings.py` actually implements and wires in.
- **`faiss-cpu`** — replaced by pgvector, which fits the multi-tenant,
  Postgres-backed persistence model without a separate index file per tenant
  to manage.
- **CLI entrypoint, Streamlit frontend, `evaluation/` harness (ROUGE,
  BERTScore, RMSE-vs-ground-truth), Docker healthcheck for a UI container** —
  not ported. These served the hackathon demo/judging format specifically;
  none are needed for a multi-tenant API product, and re-adding a real
  frontend or an evaluation-against-production-usage harness is future work,
  not a straight port.
- **Global single-tenant mock catalog (`catalog.json`, 553 sample items)** —
  replaced by per-tenant catalog upload via `POST /v1/catalog/items`.
