"""
VayuSutra APIx - Command-Line Interface (CLI) Management Tool
Enterprise DevOps operations, data ingestion, ML forecasting, anomaly scanning,
scenario simulation, and AI Policy Analyst CLI.
"""

import argparse
import asyncio
import datetime
import json
import os
import sys
import uvicorn

from .config.db import init_db
from .engine.backtest import DGCABacktestEngine
from .engine.model_trainer import train_nowcast_model
from .forecasting.engine import get_national_forecast, get_route_forecast
from .anomaly.detector import get_market_anomalies
from .analytics.pressure_score import get_inflation_pressure_score
from .analytics.cpi_decomposition import get_cpi_decomposition
from .analytics.heatmap import get_airfare_heatmap
from .scenario.simulator import simulate_policy_scenario, ScenarioInputParameters
from .data_quality.trust_score import get_latest_data_quality
from .reports.generator import get_daily_intelligence_report, export_intelligence_report
from .ai_analyst.policy_analyst import ask_ai_policy_analyst, PolicyAnalystQuery
from .scrapers.esankhyiki_connector import ESankhyikiConnector
from .services.scheduler import IngestionWorkerDaemon
from .auth import get_demo_users, authenticate_user


def cmd_auth(args):
    """List or test demo user authentication credentials."""
    init_db()
    if args.login:
        user_or_email, pwd = args.login.split(":") if ":" in args.login else (args.login, "")
        res = authenticate_user(user_or_email, pwd)
        if res:
            print(f"[+] Authentication SUCCESS: {res.user.full_name} ({res.user.role.value})")
            print(f"    Token: {res.access_token[:30]}...")
            print(f"    Permissions: {', '.join(res.user.permissions)}")
        else:
            print(f"[-] Authentication FAILED for {user_or_email}")
        return

    demos = get_demo_users()
    print("=" * 80)
    print("VAYUSUTRA APIx - OFFICIAL DEMO & RBAC CREDENTIAL REGISTRY")
    print("=" * 80)
    for u in demos:
        print(f"\n[{u.role.value}] {u.full_name}")
        print(f"  Designation : {u.designation}")
        print(f"  Organization: {u.organization}")
        print(f"  Email/Login : {u.email} (or username '{u.username}')")
        print(f"  Password    : {u.default_password}")
        print(f"  Key Features: {', '.join(u.key_features)}")
    print("=" * 80)


def cmd_serve(args):
    print(f"[*] Starting VayuSutra APIx Production Service on {args.host}:{args.port} (Workers: {args.workers})...")
    uvicorn.run("vayusutra_apix.api.main:app", host=args.host, port=args.port, workers=args.workers)


def cmd_ingest(args):
    init_db()
    from .scrapers.market_feed import MarketFeedGenerator, SimulationConfig
    from .pipeline.cleaner import DataCleaningPipeline
    from .engine.index_calculator import IndexCalculationEngine

    date_str = args.date or datetime.date.today().isoformat()
    booking_date = datetime.date.fromisoformat(date_str)
    
    print(f"[*] Executing Ingestion Cycle for {date_str}...")
    feed = MarketFeedGenerator(SimulationConfig(seed=None, anomaly_rate=0.015))
    raw_quotes = feed.generate_quotes_for_date(booking_date, day_index=1)
    
    cleaner = DataCleaningPipeline()
    cleaned_quotes, clean_sum = cleaner.process_and_clean(raw_quotes)

    calculator = IndexCalculationEngine()
    elem_results, relatives_map = calculator.compute_elementary_aggregates(cleaned_quotes, date_str)
    nat_calc = calculator.compute_national_indices(elem_results, relatives_map, date_str)

    print(f"[+] Ingestion Complete:")
    print(f"    - Raw Quotes Ingested: {clean_sum.total_raw_quotes}")
    print(f"    - Multi-OTA Duplicates Dropped: {clean_sum.duplicates_dropped}")
    print(f"    - MAD Outliers Filtered: {clean_sum.outliers_flagged}")
    print(f"    - Clean Quotes Indexed: {clean_sum.valid_quotes_retained}")
    print(f"    - Master Laspeyres Index: {nat_calc.laspeyres_index:.2f}")
    print(f"    - Fisher Ideal Index: {nat_calc.fisher_index:.2f}")
    print(f"    - Transport Sub-Group Impact: {nat_calc.bps_transport_impact:+.2f} bps")
    print(f"    - Headline CPI Impact: {nat_calc.bps_headline_cpi_impact:+.4f} bps")


def cmd_train(args):
    init_db()
    print("[*] Training Econometric Nowcast Ensemble (Ridge + GBDT)...")
    ensemble, metrics = train_nowcast_model()
    print("[+] Model Training Successful!")
    print(f"    - Model Version: {metrics.model_version}")
    print(f"    - Training R²: {metrics.r2_train:.4f}")
    print(f"    - Test RMSE: {metrics.rmse_test:.4f}")
    print(f"    - Test MAPE: {metrics.mape_test:.2f}%")
    print(f"    - Total Observations: {metrics.sample_size}")


def cmd_forecast(args):
    init_db()
    print(f"[*] Generating Multi-Model Forecast (Horizon: {args.horizon} days)...")
    if args.route:
        rep = get_route_forecast(args.route, horizon_days=args.horizon)
    else:
        rep = get_national_forecast(horizon_days=args.horizon)
    print(f"[+] Forecast Output (As of {rep.as_of_date}):")
    print(f"    - Current Index: {rep.current_index:.2f}")
    print(f"    - Champion Model: {rep.best_model_name}")
    print(f"    - Mean 30d Forecast: {rep.summary_mean_forecast_30d:.2f}")
    print(f"    - Net CPI Impact: {rep.net_headline_cpi_impact_bps:+.4f} bps")


def cmd_pressure(args):
    init_db()
    rep = get_inflation_pressure_score()
    print(f"[+] Airfare Inflation Pressure Score: {rep.pressure_score:.1f}/100 ({rep.pressure_level})")
    print(f"    - 24h Change: {rep.score_change_24h:+.1f} pts")
    print(f"    - RBI MPC Alert: {rep.rbi_monetary_policy_alert}")
    print("    - Top Drivers:")
    for d in rep.ranked_drivers[:4]:
        print(f"      • {d}")


def cmd_cpi_decomp(args):
    init_db()
    rep = get_cpi_decomposition()
    print(f"[+] Headline CPI Impact: {rep.total_headline_cpi_impact_bps:+.4f} bps (Transport: {rep.total_transport_impact_bps:+.2f} bps)")
    print("    - Top Contributors:")
    for r in rep.top_positive_contributors[:4]:
        print(f"      • {r.route_code} ({r.corridor_name}): {r.headline_cpi_impact_bps:+.4f} bps ({r.share_of_total_inflation_pct:.1f}% share)")


def cmd_anomalies(args):
    init_db()
    anoms = get_market_anomalies()
    print(f"[+] Active Market Anomalies Detected ({len(anoms)}):")
    for a in anoms:
        print(f"    - [{a['severity']}] {a['route_code']} ({a['anomaly_type']}): {a['explanation']}")


def cmd_simulate(args):
    init_db()
    params = ScenarioInputParameters(
        scenario_name=args.name,
        airfare_shock_pct=args.airfare,
        demand_change_pct=args.demand,
        capacity_change_pct=args.capacity,
        atf_fuel_shock_pct=args.fuel
    )
    res = simulate_policy_scenario(params)
    print(f"[+] Scenario Simulation Result: {res.scenario_name}")
    print(f"    - Airfare Index: {res.baseline_airfare_index:.2f} -> {res.projected_airfare_index:.2f} ({res.net_airfare_index_change_pct:+.2f}%)")
    print(f"    - CPI Transport Impact: {res.projected_transport_subgroup_impact_bps:+.2f} bps")
    print(f"    - Headline CPI Impact: {res.projected_headline_cpi_impact_bps:+.4f} bps")
    print(f"    - Projected Pressure: {res.projected_inflation_pressure_score:.1f} ({res.projected_pressure_level})")


def cmd_data_quality(args):
    init_db()
    dq = get_latest_data_quality()
    print(f"[+] Overall Data Trust Score: {dq.overall_trust_score:.1f}/100 ({dq.status_rating})")
    print(f"    - Freshness: {dq.freshness_pct:.1f}%")
    print(f"    - Completeness: {dq.completeness_pct:.1f}%")
    print(f"    - Route Coverage: {dq.route_coverage_pct:.1f}%")
    print(f"    - Source Health: {dq.source_health_pct:.1f}%")
    print(f"    - Outlier Cleanliness: {100.0 - dq.outlier_rate_pct*5.0:.1f}%")


def cmd_ask(args):
    init_db()
    q = PolicyAnalystQuery(question=args.question)
    res = ask_ai_policy_analyst(q)
    print(f"\n[?] Question: {res.question}")
    print(f"[🎯] Intent: {res.detected_intent}")
    print(f"\n[💡] Answer Summary:\n{res.answer_summary}")
    print(f"\n[📊] Detailed Explanation:\n{res.detailed_explanation}")
    print(f"\n[🏷️] Data Tag: {res.data_tag} | Timestamp: {res.timestamp}\n")


def cmd_report(args):
    init_db()
    rep = get_daily_intelligence_report()
    print(f"[+] Report ID: {rep.report_id} ({rep.publication_date})")
    print(f"    {rep.executive_summary}")


def cmd_backtest(args):
    init_db()
    engine = DGCABacktestEngine()
    res = engine.run_backtest(num_days=args.days)
    print(f"[+] Backtest Validation Report ({res.sample_days} Days / {res.total_quotes_evaluated:,} Quotes):")
    print(f"    - Pearson r: {res.pearson_r:.4f} (Mandate >0.85)")
    print(f"    - MAPE: {res.mape:.2f}% (Mandate <4.0%)")
    print(f"    - R²: {res.r2:.4f} (Mandate >0.75)")
    print(f"    - Status: {res.validation_status}")


def cmd_worker(args):
    init_db()
    print(f"[*] Launching Standalone Ingestion Worker Daemon (Interval: {args.interval}s)...")
    daemon = IngestionWorkerDaemon(interval_seconds=args.interval)
    daemon.start()

    async def main_loop():
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            daemon.stop()
            print("\n[*] Daemon terminated.")

    asyncio.run(main_loop())


def main():
    parser = argparse.ArgumentParser(
        prog="vayusutra",
        description="VayuSutra APIx - National Airfare Intelligence & Inflation Decision Platform CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # serve
    p_serve = subparsers.add_parser("serve", help="Start FastAPI production server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--workers", type=int, default=1)
    p_serve.set_defaults(func=cmd_serve)

    # ingest
    p_ingest = subparsers.add_parser("ingest", help="Run on-demand scraping & calculation")
    p_ingest.add_argument("--date", help="Optional YYYY-MM-DD date")
    p_ingest.set_defaults(func=cmd_ingest)

    # train
    p_train = subparsers.add_parser("train", help="Train AI Nowcast ML Ensemble")
    p_train.set_defaults(func=cmd_train)

    # forecast
    p_fc = subparsers.add_parser("forecast", help="Generate forward forecast")
    p_fc.add_argument("--horizon", type=int, default=14)
    p_fc.add_argument("--route", help="Optional route code")
    p_fc.set_defaults(func=cmd_forecast)

    # pressure
    p_press = subparsers.add_parser("pressure", help="Get Inflation Pressure Score")
    p_press.set_defaults(func=cmd_pressure)

    # cpi-decomp
    p_dec = subparsers.add_parser("cpi-decomp", help="Get CPI route contribution waterfall")
    p_dec.set_defaults(func=cmd_cpi_decomp)

    # anomalies
    p_anom = subparsers.add_parser("anomalies", help="Scan active market anomalies")
    p_anom.set_defaults(func=cmd_anomalies)

    # simulate
    p_sim = subparsers.add_parser("simulate", help="Run policy what-if scenario")
    p_sim.add_argument("--name", default="CLI Policy Shock")
    p_sim.add_argument("--airfare", type=float, default=10.0)
    p_sim.add_argument("--demand", type=float, default=5.0)
    p_sim.add_argument("--capacity", type=float, default=-3.0)
    p_sim.add_argument("--fuel", type=float, default=12.0)
    p_sim.set_defaults(func=cmd_simulate)

    # data-quality
    p_dq = subparsers.add_parser("data-quality", help="Inspect Data Trust Scorecard")
    p_dq.set_defaults(func=cmd_data_quality)

    # ask
    p_ask = subparsers.add_parser("ask", help="Query the AI Policy Analyst")
    p_ask.add_argument("question", help="Question text")
    p_ask.set_defaults(func=cmd_ask)

    # report
    p_rep = subparsers.add_parser("report", help="Generate Daily Intelligence Brief")
    p_rep.set_defaults(func=cmd_report)

    # backtest
    p_bt = subparsers.add_parser("backtest", help="Run DGCA backtesting validation")
    p_bt.add_argument("--days", type=int, default=35)
    p_bt.set_defaults(func=cmd_backtest)

    # worker
    p_w = subparsers.add_parser("worker", help="Run background daemon")
    p_w.add_argument("--interval", type=int, default=60)
    p_w.set_defaults(func=cmd_worker)

    # auth
    p_auth = subparsers.add_parser("auth", help="List and verify RBAC credentials")
    p_auth.add_argument("--login", help="Test credentials in format user:password")
    p_auth.set_defaults(func=cmd_auth)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
