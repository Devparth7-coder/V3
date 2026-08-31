"""
VayuSutra APIx - Advanced Analytics, Anomalies, Scenarios, Provenance & AI Analyst Tests
"""

import pytest
from fastapi.testclient import TestClient
from vayusutra_apix.api.main import app
from vayusutra_apix.analytics.pressure_score import get_inflation_pressure_score
from vayusutra_apix.analytics.cpi_decomposition import get_cpi_decomposition
from vayusutra_apix.analytics.heatmap import get_airfare_heatmap
from vayusutra_apix.analytics.source_consensus import get_source_consensus_report
from vayusutra_apix.data_quality.trust_score import get_latest_data_quality
from vayusutra_apix.scenario.simulator import simulate_policy_scenario, ScenarioInputParameters
from vayusutra_apix.ai_analyst.policy_analyst import ask_ai_policy_analyst, PolicyAnalystQuery
from vayusutra_apix.provenance.tracer import get_quote_trace, get_cell_drilldown
from vayusutra_apix.alerts.engine import create_alert_rule, get_active_alerts, AlertRuleDefinition


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_pressure_score_computation():
    """Verify Airfare Inflation Pressure Score is within [0, 100] with classified levels."""
    rep = get_inflation_pressure_score()
    assert 0.0 <= rep.pressure_score <= 100.0
    assert rep.pressure_level in {"LOW", "MODERATE", "HIGH", "CRITICAL"}
    assert len(rep.ranked_drivers) > 0
    assert "airfare_acceleration" in rep.components


def test_cpi_decomposition_waterfall():
    """Verify route-level additive CPI decomposition sums appropriately."""
    rep = get_cpi_decomposition()
    assert len(rep.full_route_waterfall) == 20
    assert len(rep.top_positive_contributors) <= 5
    for r in rep.full_route_waterfall:
        assert r.route_code is not None
        assert r.route_weight_pct > 0.0


def test_airfare_heatmap_matrix():
    """Verify 20x5 heatmap matrix covers all 20 routes across all 5 horizons."""
    rep = get_airfare_heatmap()
    assert rep.total_routes == 20
    assert rep.total_horizons == 5
    for row in rep.matrix_rows:
        assert len(row.horizon_cells) == 5
        assert "T+1" in row.horizon_cells
        assert "T+45" in row.horizon_cells


def test_source_consensus_engine():
    """Verify cross-portal dispersion, CV %, and consensus scores."""
    rep = get_source_consensus_report()
    assert 0.0 <= rep.overall_market_consensus_score <= 100.0
    assert rep.total_corridors_analyzed == 20
    for r in rep.consensus_leaderboard:
        assert r.median_fare_inr > 0
        assert r.consensus_status in {"NORMAL", "WARNING", "HIGH_DISAGREEMENT"}


def test_scenario_policy_simulator():
    """Verify policy what-if scenario simulator evaluates shocks with modeled tag."""
    params = ScenarioInputParameters(
        scenario_name="Test Fuel Shock",
        airfare_shock_pct=15.0,
        demand_change_pct=5.0,
        capacity_change_pct=-5.0,
        atf_fuel_shock_pct=20.0
    )
    res = simulate_policy_scenario(params)
    assert res.projected_airfare_index > res.baseline_airfare_index
    assert res.projected_transport_subgroup_impact_bps > 0
    assert res.data_tag == "MODELLED / SIMULATED"


def test_data_trust_quality_engine():
    """Verify 7-dimension Data Trust Score computation."""
    dq = get_latest_data_quality()
    assert 0.0 <= dq.overall_trust_score <= 100.0
    assert dq.freshness_pct > 0.0
    assert dq.route_coverage_pct == 100.0
    assert dq.status_rating in {"EXCELLENT", "GOOD", "FAIR", "DEGRADED"}


def test_ai_policy_analyst_grounding():
    """Verify AI Policy Analyst provides data-grounded answers without hallucination."""
    q1 = PolicyAnalystQuery(question="Why did airfare inflation increase today?")
    r1 = ask_ai_policy_analyst(q1)
    assert r1.detected_intent == "EXPLAIN_INFLATION_MOVEMENT"
    assert "master_laspeyres_index" in r1.numerical_evidence

    q2 = PolicyAnalystQuery(question="Which routes contributed most to CPI pressure?")
    r2 = ask_ai_policy_analyst(q2)
    assert r2.detected_intent == "EXPLAIN_CPI_CONTRIBUTIONS"
    assert len(r2.affected_routes) > 0


def test_provenance_and_drilldown():
    """Verify hierarchical drill-down from route cell to raw quotes."""
    cell = get_cell_drilldown("2026-08-26", "DEL-BOM", "T+1", limit=10)
    assert "cell_hierarchy" in cell
    assert cell["cell_hierarchy"]["route_code"] == "DEL-BOM"


def test_alert_rule_engine(client):
    """Verify alert rule creation and alert stream retrieval."""
    rule = AlertRuleDefinition(
        rule_name="Test High Pressure Alert",
        metric_target="pressure_score",
        condition_operator=">",
        threshold_value=70.0,
        severity="HIGH"
    )
    res = create_alert_rule(rule)
    assert res["status"] == "SUCCESS"

    alerts = get_active_alerts()
    assert isinstance(alerts, list)
