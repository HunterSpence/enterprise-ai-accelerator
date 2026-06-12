"""Tests for core/model_router.py — route() per task kind, stats, overrides."""

from core.model_router import ModelRouter, RoutingTask
from core.models import MODEL_HAIKU_4_5, MODEL_OPUS_4_7, MODEL_SONNET_4_6


class TestModelRouterRouting:
    def setup_method(self):
        self.router = ModelRouter()

    def test_default_routes_to_sonnet(self):
        model = self.router.route(RoutingTask(kind="generic"))
        assert model == MODEL_SONNET_4_6

    def test_classification_routes_to_haiku(self):
        model = self.router.route(RoutingTask(kind="classification"))
        assert model == MODEL_HAIKU_4_5

    def test_extraction_routes_to_haiku(self):
        model = self.router.route(RoutingTask(kind="extraction"))
        assert model == MODEL_HAIKU_4_5

    def test_simple_summary_routes_to_haiku(self):
        model = self.router.route(RoutingTask(kind="simple_summary"))
        assert model == MODEL_HAIKU_4_5

    def test_tagging_routes_to_haiku(self):
        model = self.router.route(RoutingTask(kind="tagging"))
        assert model == MODEL_HAIKU_4_5

    def test_entity_extraction_routes_to_haiku(self):
        model = self.router.route(RoutingTask(kind="entity_extraction"))
        assert model == MODEL_HAIKU_4_5

    def test_annex_iv_routes_to_opus(self):
        model = self.router.route(RoutingTask(requires_annex_iv_audit=True))
        assert model == MODEL_OPUS_4_7

    def test_large_context_routes_to_sonnet(self):
        # Sonnet 4.6 matches Fable 5's 1M context window at 30% of the input
        # price — long-context tasks route to the cheapest capable model.
        model = self.router.route(RoutingTask(token_count_estimate=500_000))
        assert model == MODEL_SONNET_4_6

    def test_large_context_never_routes_to_haiku(self):
        # Haiku-eligible kind, but the task exceeds Haiku's 200K window.
        model = self.router.route(
            RoutingTask(kind="classification", token_count_estimate=250_000)
        )
        assert model == MODEL_SONNET_4_6

    def test_route_decision_carries_effort(self):
        from core.model_router import RoutingDecision
        from core.models import EFFORT_XHIGH

        decision = self.router.route_decision(RoutingTask(requires_annex_iv_audit=True))
        assert isinstance(decision, RoutingDecision)
        assert decision.model == MODEL_OPUS_4_7
        assert decision.effort == EFFORT_XHIGH

    def test_haiku_decision_has_no_effort(self):
        # Haiku 4.5 errors on the effort parameter — the router must not
        # recommend one.
        decision = self.router.route_decision(RoutingTask(kind="extraction"))
        assert decision.model == MODEL_HAIKU_4_5
        assert decision.effort is None

    def test_executive_prose_routes_to_sonnet(self):
        model = self.router.route(RoutingTask(needs_executive_prose=True))
        assert model == MODEL_SONNET_4_6

    def test_override_model_wins(self):
        model = self.router.route(RoutingTask(kind="extraction", override_model=MODEL_OPUS_4_7))
        assert model == MODEL_OPUS_4_7

    def test_override_beats_annex_iv(self):
        model = self.router.route(RoutingTask(
            requires_annex_iv_audit=True, override_model=MODEL_HAIKU_4_5
        ))
        assert model == MODEL_HAIKU_4_5

    def test_annex_iv_beats_large_context(self):
        # annex_iv (Fable 5) is checked before the long-context rule (Sonnet)
        model = self.router.route(RoutingTask(
            requires_annex_iv_audit=True, token_count_estimate=500_000
        ))
        assert model == MODEL_OPUS_4_7


class TestModelRouterStats:
    def setup_method(self):
        self.router = ModelRouter()

    def test_stats_returns_per_model_keys(self):
        self.router.route(RoutingTask(kind="extraction"))
        s = self.router.stats()
        assert "per_model" in s
        assert MODEL_HAIKU_4_5 in s["per_model"]

    def test_stats_call_count_increments(self):
        self.router.route(RoutingTask(kind="extraction"))
        self.router.route(RoutingTask(kind="extraction"))
        s = self.router.stats()
        assert s["per_model"][MODEL_HAIKU_4_5]["calls"] == 2

    def test_reset_clears_stats(self):
        self.router.route(RoutingTask(kind="extraction"))
        self.router.reset_stats()
        s = self.router.stats()
        assert s["per_model"][MODEL_HAIKU_4_5]["calls"] == 0

    def test_savings_nonnegative_after_haiku_calls(self):
        self.router.route(RoutingTask(kind="extraction", token_count_estimate=1000))
        s = self.router.stats()
        assert s["savings_usd"] >= 0.0

    def test_token_estimate_accumulated(self):
        self.router.route(RoutingTask(kind="extraction", token_count_estimate=500))
        self.router.route(RoutingTask(kind="extraction", token_count_estimate=300))
        s = self.router.stats()
        assert s["per_model"][MODEL_HAIKU_4_5]["input_tokens_est"] == 800
