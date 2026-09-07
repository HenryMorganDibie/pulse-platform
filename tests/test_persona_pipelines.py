"""
Unit tests for the pure-logic persona pipelines (behavioural, contextual —
no Groq call, no DB). The textual pipeline needs a live GROQ_API_KEY and is
covered separately as an integration test, not here.
"""

from __future__ import annotations

import pytest

from src.persona.models import ReviewRecord
from src.persona.pipelines import _behavioural_pipeline, _contextual_pipeline


def _record(category: str, rating: float, timestamp: str | None = None) -> ReviewRecord:
    return ReviewRecord(item_id="i_1", category=category, rating=rating, text="fine", timestamp=timestamp)


class TestBehaviouralPipeline:
    @pytest.mark.asyncio
    async def test_empty_history_returns_neutral_fallback(self):
        profile = await _behavioural_pipeline([])
        assert profile.avg_rating == 3.0
        assert profile.category_affinities == {}
        assert not profile.is_harsh_rater
        assert not profile.is_generous_rater

    @pytest.mark.asyncio
    async def test_avg_and_bias(self):
        history = [_record("Food", 4.0), _record("Food", 5.0)]
        profile = await _behavioural_pipeline(history)
        assert profile.avg_rating == 4.5
        assert profile.rating_bias == round(4.5 - 3.7, 2)

    @pytest.mark.asyncio
    async def test_harsh_and_generous_thresholds(self):
        harsh = await _behavioural_pipeline([_record("Food", 2.0), _record("Food", 2.5)])
        generous = await _behavioural_pipeline([_record("Food", 4.5), _record("Food", 5.0)])
        assert harsh.is_harsh_rater and not harsh.is_generous_rater
        assert generous.is_generous_rater and not generous.is_harsh_rater

    @pytest.mark.asyncio
    async def test_category_affinity_normalises_to_one(self):
        history = [_record("Food", 4.0), _record("Food", 4.0), _record("Books", 3.0)]
        profile = await _behavioural_pipeline(history)
        assert profile.category_affinities["Food"] == pytest.approx(2 / 3)
        assert profile.category_affinities["Books"] == pytest.approx(1 / 3)


class TestContextualPipeline:
    @pytest.mark.asyncio
    async def test_no_history_is_cold_start(self):
        profile = await _contextual_pipeline([])
        assert profile.is_cold_start
        assert profile.sparse_history

    @pytest.mark.asyncio
    async def test_sparse_below_five_reviews(self):
        history = [_record("Food", 4.0) for _ in range(3)]
        profile = await _contextual_pipeline(history)
        assert not profile.is_cold_start
        assert profile.sparse_history

    @pytest.mark.asyncio
    async def test_not_sparse_at_five_reviews(self):
        history = [_record("Food", 4.0) for _ in range(5)]
        profile = await _contextual_pipeline(history)
        assert not profile.sparse_history

    @pytest.mark.asyncio
    async def test_cross_domain_signals_exclude_top_two_categories(self):
        history = (
            [_record("Food", 4.0) for _ in range(5)]
            + [_record("Nightlife", 4.0) for _ in range(3)]
            + [_record("Books", 4.0)]
        )
        profile = await _contextual_pipeline(history)
        assert "Books" in profile.cross_domain_signals
        assert "Food" not in profile.cross_domain_signals
        assert "Nightlife" not in profile.cross_domain_signals
