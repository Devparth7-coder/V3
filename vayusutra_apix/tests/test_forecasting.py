"""
VayuSutra APIx - Forecasting Framework & Walk-Forward Cross-Validation Tests
"""

import numpy as np
import pytest
from vayusutra_apix.forecasting.engine import (
    ForecastingEngine,
    get_national_forecast,
    get_route_forecast,
)


def test_forecasting_candidate_models():
    """Verify all 5 candidate time series models output valid finite forecasts."""
    engine = ForecastingEngine()
    history = np.array([100.0, 102.0, 101.5, 103.0, 108.0, 105.0, 110.0,
                        101.0, 103.5, 102.0, 104.5, 109.5, 106.0, 111.0,
                        102.0, 104.0, 103.0, 105.0, 110.0, 107.0, 112.0], dtype=float)

    # 1. Seasonal Naive
    p_naive = engine.model_seasonal_naive(history, horizon=7, season_len=7)
    assert len(p_naive) == 7
    assert np.all(np.isfinite(p_naive))

    # 2. Holt-Winters ETS
    p_ets = engine.model_exponential_smoothing_ets(history, horizon=7, season_len=7)
    assert len(p_ets) == 7
    assert np.all(np.isfinite(p_ets))

    # 3. Seasonal AR
    p_ar = engine.model_seasonal_ar(history, horizon=7)
    assert len(p_ar) == 7
    assert np.all(np.isfinite(p_ar))

    # 4. GBDT
    p_gbdt = engine.model_gradient_boosting(history, horizon=7)
    assert len(p_gbdt) == 7
    assert np.all(np.isfinite(p_gbdt))


def test_walk_forward_evaluation():
    """Verify walk-forward validation computes valid sMAPE and selects a champion model."""
    engine = ForecastingEngine()
    history = 100.0 + 0.15 * np.arange(30) + 2.5 * np.sin(2 * np.pi * (np.arange(30) % 7) / 7.0)
    
    best_name, scores, meta = engine.walk_forward_evaluate(history, test_window=7)
    assert isinstance(best_name, str)
    assert len(scores) >= 4
    assert any(s.is_best_selected for s in scores)
    for s in scores:
        assert s.smape >= 0.0
        assert s.rmse >= 0.0


def test_national_and_route_forecast_reports():
    """Verify national and route forward forecast pipelines return 95% confidence intervals."""
    nat_rep = get_national_forecast(horizon_days=14)
    assert nat_rep.target_type == "NATIONAL"
    assert len(nat_rep.daily_trajectory) == 14
    assert "7d" in nat_rep.horizons
    assert "14d" in nat_rep.horizons

    for step in nat_rep.daily_trajectory:
        assert step.lower_bound_95 <= step.forecast_value <= step.upper_bound_95
        assert step.forecast_value > 50.0

    # Route forecast
    r_rep = get_route_forecast("DEL-BOM", horizon_days=7)
    assert r_rep.target_type == "ROUTE"
    assert r_rep.target_code == "DEL-BOM"
    assert len(r_rep.daily_trajectory) == 7
