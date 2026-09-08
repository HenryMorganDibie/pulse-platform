"""
Tests for the deterministic, customer-safe decision_factors derivation used
by both products. These must never contain raw exception text or LLM
free-text — see CONTRACTS.md's "Adapted" section for why this replaced the
old reasoning_trace field.
"""

from __future__ import annotations

from src.persona.models import BehaviouralProfile, ContextualProfile, TextualProfile, ToneProfile, UserState
from src.products.recommend.service import decision_factors as recommend_factors
from src.products.simulate.agent import _decision_factors as simulate_factors
from src.schemas.api import ItemDetailsIn


def _user_state(**overrides) -> UserState:
    defaults = dict(
        subject_id="s_1",
        behavioural=BehaviouralProfile(
            avg_rating=4.0,
            rating_std=0.5,
            category_affinities={"Food": 0.8, "Books": 0.2},
            recency_weighted_avg=4.0,
            rating_bias=0.3,
            is_harsh_rater=False,
            is_generous_rater=False,
        ),
        textual=TextualProfile(
            dominant_tone=ToneProfile.EXPRESSIVE,
            avg_review_length=40,
            sentiment_polarity=0.5,
            vocabulary_richness=0.5,
            uses_first_person=True,
        ),
        contextual=ContextualProfile(
            is_cold_start=False,
            sparse_history=False,
            active_categories=["Food", "Books"],
            cross_domain_signals=[],
        ),
    )
    defaults.update(overrides)
    return UserState(**defaults)


class TestSimulateDecisionFactors:
    def test_no_exception_text_or_fallback_language_leaks(self):
        item = ItemDetailsIn(item_id="i_1", name="The Grill House", category="Food")
        factors = simulate_factors(_user_state(), item, 4.2)
        joined = " ".join(factors).lower()
        assert "traceback" not in joined
        assert "exception" not in joined
        assert "error" not in joined

    def test_known_category_cites_affinity(self):
        item = ItemDetailsIn(item_id="i_1", name="The Grill House", category="Food")
        factors = simulate_factors(_user_state(), item, 4.2)
        assert any("Food" in f for f in factors)

    def test_cold_start_subject_notes_no_history(self):
        item = ItemDetailsIn(item_id="i_1", name="New Spot", category="Nightlife")
        state = _user_state(
            behavioural=BehaviouralProfile(
                avg_rating=3.0, rating_std=0.0, category_affinities={},
                recency_weighted_avg=3.0, rating_bias=0.0,
                is_harsh_rater=False, is_generous_rater=False,
            ),
            contextual=ContextualProfile(
                is_cold_start=True, sparse_history=True,
                active_categories=[], cross_domain_signals=[],
            ),
        )
        factors = simulate_factors(state, item, 3.0)
        assert any("no prior history" in f.lower() for f in factors)


class TestRecommendDecisionFactors:
    def test_cold_start_strategy_explained(self):
        factors = recommend_factors(_user_state(contextual=ContextualProfile(
            is_cold_start=True, sparse_history=True, active_categories=[], cross_domain_signals=[],
        )), "cold_start", "something chill for the weekend")
        assert any("no prior history" in f.lower() for f in factors)

    def test_normal_strategy_cites_top_categories(self):
        factors = recommend_factors(_user_state(), "normal", "date night")
        assert any("Food" in f for f in factors)
