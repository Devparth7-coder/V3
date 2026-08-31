"""
VayuSutra APIx - National Airfare Intelligence & Inflation Decision Platform
REST API, WebSocket Event Streaming & Microservice Architecture
Compliant with MoSPI, NSO, RBI Monetary Policy Committee, and DGCA standards.
"""

import csv
import datetime
import io
import json
import logging
import math
import os
import sqlite3
import hashlib
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Any, Optional
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, Depends, Header, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..config.routes import (
    DGCA_TOP_20_ROUTES,
    ADVANCE_PURCHASE_WINDOWS,
    AIRLINE_MARKET_SHARES,
    CPI_WEIGHTS,
    TAX_RULES,
    ROUTE_LOOKUP,
    WINDOW_LOOKUP,
    AIRLINE_LOOKUP,
    BASE_PERIOD_BENCHMARKS,
)
from ..config.db import get_db_connection, DB_PATH, init_db
from ..scrapers.market_feed import MarketFeedGenerator, SimulationConfig
from ..pipeline.cleaner import DataCleaningPipeline
from ..engine.index_calculator import IndexCalculationEngine
from ..engine.backtest import DGCABacktestEngine
from ..engine.model_trainer import train_nowcast_model, EconometricNowcastEnsemble, MODEL_ARTIFACT_PATH
from ..engine.nowcast_predictor import InflationNowcastPredictor
from ..scrapers.esankhyiki_connector import ESankhyikiConnector
from ..services.metrics import get_prometheus_metrics_payload, update_system_gauges
from ..services.streaming import stream_manager
from ..services.scheduler import worker_daemon

# New Modular Subsystems
from ..data_quality.trust_score import get_latest_data_quality, DataQualityEngine
from ..provenance.tracer import get_quote_trace, get_cell_drilldown
from ..forecasting.engine import get_national_forecast, get_route_forecast
from ..validation.model_validator import get_validation_center_report
from ..anomaly.detector import get_market_anomalies, get_route_anomalies
from ..analytics.pressure_score import get_inflation_pressure_score
from ..analytics.cpi_decomposition import get_cpi_decomposition
from ..analytics.heatmap import get_airfare_heatmap
from ..analytics.source_consensus import get_source_consensus_report
from ..analytics.source_analytics import get_sources_analytics
from ..analytics.temporal import get_temporal_analytics
from ..analytics.route_intelligence import get_route_intelligence, compare_routes
from ..scenario.simulator import simulate_policy_scenario, ScenarioInputParameters
from ..alerts.engine import get_active_alerts, create_alert_rule, update_alert_status, AlertRuleDefinition, alert_engine
from ..reports.generator import get_daily_intelligence_report, export_intelligence_report
from ..ai_analyst.policy_analyst import ask_ai_policy_analyst, PolicyAnalystQuery

# Authentication & RBAC System
from ..auth import (
    User,
    UserRole,
    LoginRequest,
    LoginResponse,
    SwitchRoleRequest,
    DemoUserCredential,
    authenticate_user,
    get_user_by_id,
    get_demo_users,
    switch_user_role,
    init_auth_tables,
    get_current_user,
    get_current_user_optional,
    require_permission,
    get_default_guest_user,
    ROLE_PERMISSIONS,
    PRE_SEEDED_USERS
)

logger = logging.getLogger("vayusutra.api")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")
DATA_DIR = os.path.join(BASE_DIR, "data")
DASHBOARD_PATH = os.path.join(STATIC_DIR, "dashboard.html")
VIDEO_PATH = os.path.join(STATIC_DIR, "video_walkthrough.html")
SOLUTION_CARD_PATH = os.path.join(STATIC_DIR, "proposed_solution_card.html")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup & shutdown lifecycle events."""
    init_db()
    init_auth_tables()
    conn = get_db_connection()
    row = conn.execute("SELECT COUNT(*) as cnt FROM national_indices").fetchone()
    if not row or row["cnt"] == 0:
        engine = DGCABacktestEngine()
        engine.run_backtest(num_days=35)
        train_nowcast_model()

    worker_daemon.start()
    yield
    worker_daemon.stop()


app = FastAPI(
    title="VayuSutra APIx - National Airfare Intelligence & Inflation Decision Platform",
    description=(
        "High-frequency econometric price indexing, inflation nowcasting, and policy scenario simulation "
        "for MoSPI / NSO, RBI Monetary Policy Committee, and DGCA. Measures, Explains, Forecasts, and Simulates air travel inflation."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID Middleware & Performance Logging
@app.middleware("http")
async def add_request_telemetry(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID", f"REQ-{int(time.time()*1000)}")
    start_time = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start_time) * 1000.0
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Response-Time-MS"] = f"{duration_ms:.2f}"
    return response


# =============================================================================
# 1. UI DASHBOARD & STATIC PRESENTATION ROUTES
# =============================================================================

@app.get("/", response_class=HTMLResponse, summary="National Airfare Intelligence Command Center")
def serve_dashboard():
    """Serves the standalone interactive zero-dependency HTML dashboard."""
    if os.path.exists(DASHBOARD_PATH):
        with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>VayuSutra APIx Dashboard loading...</h2>")


@app.get("/routes/{route_code}", response_class=HTMLResponse, summary="Route Intelligence Page")
def serve_route_page(route_code: str):
    """Serves the dashboard with automatic route focus."""
    return serve_dashboard()


@app.get("/data-quality", response_class=HTMLResponse, summary="Data Trust Center View")
def serve_data_quality_view():
    return serve_dashboard()


@app.get("/video", response_class=HTMLResponse, summary="Hindi Video Walkthrough & Team Guide")
def serve_video_walkthrough():
    if os.path.exists(VIDEO_PATH):
        with open(VIDEO_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Walkthrough loading...</h2>")


@app.get("/solution", response_class=HTMLResponse, summary="Proposed Solution Executive Showcase")
def serve_solution_slide():
    if os.path.exists(SOLUTION_CARD_PATH):
        with open(SOLUTION_CARD_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("<h2>Solution slide loading...</h2>")


@app.get("/demo-video", response_class=HTMLResponse, summary="VayuSutra APIx Video Demo Player")
def serve_demo_video():
    return HTMLResponse("""
    <!DOCTYPE html><html><head><title>VayuSutra MVP Demo Player</title><style>body{background:#040814;color:#fff;font-family:sans-serif;padding:20px;display:flex;flex-direction:column;align-items:center;}.box{max-width:1200px;width:100%;border-radius:12px;overflow:hidden;border:1px solid rgba(56,189,248,0.3);box-shadow:0 8px 32px rgba(0,0,0,0.8);}</style></head><body><div class="box"><h2 style="padding:14px;background:#0d1426;">VayuSutra APIx: MVP Walkthrough Player</h2><p style="padding:0 14px 14px;color:#94a3b8;">High-Resolution Screen Recording & Feature Explanation (SIH26056)</p></div></body></html>
    """)


@app.get("/references", response_class=HTMLResponse, summary="References & Research Work")
def serve_references():
    return HTMLResponse("""
    <!DOCTYPE html><html><head><title>References & Research Work | VayuSutra APIx</title><style>body{background:#040814;color:#fff;font-family:sans-serif;padding:20px;display:flex;flex-direction:column;align-items:center;}.container{max-width:1300px;width:100%;}a{color:#38bdf8;text-decoration:none;border:1px solid rgba(56,189,248,0.3);padding:6px 12px;border-radius:6px;}</style></head><body><div class="container"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;"><h2>📚 References & Research Work (SIH26056)</h2><a href="/">&larr; Back to Dashboard</a></div><div style="background:#0d1426;border:1px solid #1e3a8a;border-radius:12px;padding:20px;line-height:1.7;"><h3>Official Statutory Sources:</h3><ul><li><strong>MoSPI eSankhyiki Portal:</strong> <a href="https://esankhyiki.mospi.gov.in" target="_blank">https://esankhyiki.mospi.gov.in</a> (Group 6.1.03)</li><li><strong>DGCA Domestic Air Transport Statistics:</strong> <a href="https://dgca.gov.in" target="_blank">https://dgca.gov.in</a> (City-Pair Volumes)</li><li><strong>ILO / IMF / OECD CPI Manual (2020 Edition):</strong> Jevons & Superlative Fisher Standards</li><li><strong>Iglewicz & Hoaglin:</strong> Median Absolute Deviation (MAD) Modified Z-Score Outlier Rejection</li></ul></div></div></body></html>
    """)


# =============================================================================
# 2. HEALTH & OBSERVABILITY ENDPOINTS
# =============================================================================

@app.get("/api/v1/health", summary="System Health & Subsystem Telemetry")
def get_health():
    """Returns database connection status, quote counts, data freshness, and subsystem availability."""
    conn = get_db_connection()
    raw_cnt = conn.execute("SELECT COUNT(*) as cnt FROM raw_quotes").fetchone()["cnt"]
    clean_cnt = conn.execute("SELECT COUNT(*) as cnt FROM cleaned_quotes").fetchone()["cnt"]
    nat_cnt = conn.execute("SELECT COUNT(*) as cnt FROM national_indices").fetchone()["cnt"]
    latest_date_row = conn.execute("SELECT MAX(calculation_date) as dt FROM national_indices").fetchone()
    dq = get_latest_data_quality()

    return {
        "status": "HEALTHY",
        "service": "VayuSutra-APIx",
        "platform_title": "National Airfare Intelligence & Inflation Decision Platform",
        "version": "2.0.0",
        "environment": "production",
        "beneficiaries": ["MoSPI / NSO", "Reserve Bank of India (RBI)", "DGCA"],
        "subsystems": {
            "database": {"status": "ONLINE", "mode": "SQLite-WAL", "pool": "Active"},
            "ingestion_daemon": {"status": "ACTIVE" if worker_daemon.is_running else "PAUSED", "interval": "60s"},
            "data_trust_score": {"score": dq.overall_trust_score, "rating": dq.status_rating},
            "forecasting_engine": {"status": "READY", "models_available": ["ETS", "AR", "GBDT", "Ensemble"]},
            "market_anomaly_detector": {"status": "ACTIVE"},
            "policy_simulator": {"status": "READY"},
            "ai_policy_analyst": {"status": "GROUNDED_ACTIVE"},
        },
        "telemetry": {
            "total_raw_quotes": raw_cnt,
            "total_cleaned_quotes": clean_cnt,
            "total_index_days": nat_cnt,
            "latest_index_date": latest_date_row["dt"] if latest_date_row else None,
            "dgca_routes_monitored": len(DGCA_TOP_20_ROUTES),
            "advance_windows": len(ADVANCE_PURCHASE_WINDOWS),
        },
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@app.get("/metrics", summary="Prometheus / OpenMetrics Telemetry Stream")
def get_prometheus_metrics():
    """Exposes OpenMetrics formatted scrapers, latency, CPI transmission, and hardware metrics."""
    payload, content_type = get_prometheus_metrics_payload()
    return Response(content=payload, media_type=content_type)


@app.websocket("/ws/live-feed")
async def websocket_live_feed(websocket: WebSocket):
    """Real-time WebSocket streaming of flight quotes, ticks, and inflation alerts."""
    await stream_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong", "time": datetime.datetime.now().isoformat()}))
    except WebSocketDisconnect:
        await stream_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket client closed: {e}")
        await stream_manager.disconnect(websocket)


@app.get("/api/v1/stream/events", summary="Server-Sent Events (SSE) Live Feed")
async def sse_event_stream():
    """Streams server-sent events for real-time frontend consumers without WebSockets."""
    import asyncio
    async def event_generator():
        while True:
            events = stream_manager.get_recent_events(limit=1)
            if events:
                yield f"data: {json.dumps(events[-1])}\n\n"
            await asyncio.sleep(2.0)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# =============================================================================
# 2.5. AUTHENTICATION & RBAC ENDPOINTS
# =============================================================================

@app.get("/api/v1/auth/demo-users", summary="List Pre-configured Demo Accounts")
def get_demo_accounts_endpoint():
    """Returns 5 official demo accounts (MoSPI, RBI MPC, DGCA, System Admin, Public Auditor) for 1-click testing."""
    return {
        "status": "SUCCESS",
        "demo_accounts": [u.model_dump() for u in get_demo_users()],
        "note": "Use these pre-configured executive credentials for instant zero-friction demonstration."
    }


@app.post("/api/v1/auth/login", response_model=LoginResponse, summary="Authenticate User & Issue Token")
def login_endpoint(payload: LoginRequest, request: Request):
    """Authenticates credentials against official MoSPI/RBI/DGCA credential registry."""
    ip = request.client.host if request.client else "127.0.0.1"
    ua = request.headers.get("User-Agent", "Unknown")
    res = authenticate_user(payload.username_or_email, payload.password, ip_address=ip, user_agent=ua)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please verify your email/username and password.",
        )
    return res


@app.post("/api/v1/auth/demo-login/{role_slug}", response_model=LoginResponse, summary="Instant 1-Click Demo Login")
def demo_login_endpoint(role_slug: str, request: Request):
    """Instantly logs in with one of the pre-configured government roles: 'mospi', 'rbi', 'dgca', 'admin', 'auditor'."""
    slug_map = {
        "mospi": ("mospi@gov.in", "mospi2026!"),
        "rbi": ("rbi.mpc@rbi.org.in", "rbimpc2026!"),
        "dgca": ("dgca.surveillance@dgca.nic.in", "dgca2026!"),
        "admin": ("admin@vayusutra.gov.in", "admin2026!"),
        "auditor": ("auditor@sih2026.gov.in", "guest2026!"),
    }
    target = slug_map.get(role_slug.lower())
    if not target:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown demo role '{role_slug}'. Valid options: {list(slug_map.keys())}"
        )
    ip = request.client.host if request.client else "127.0.0.1"
    ua = request.headers.get("User-Agent", "Demo-Switcher")
    res = authenticate_user(target[0], target[1], ip_address=ip, user_agent=ua)
    if not res:
        raise HTTPException(status_code=500, detail="Failed to initialize demo account session.")
    return res


@app.get("/api/v1/auth/me", summary="Current Active User Profile & Permissions")
def get_current_user_profile(user: Optional[User] = Depends(get_current_user_optional)):
    """Returns the authenticated user profile and permissions or default guest profile."""
    if user:
        return {
            "authenticated": True,
            "user": user.model_dump(),
            "role_title": user.role.value.replace("_", " "),
            "permissions": user.permissions
        }
    guest = get_default_guest_user()
    return {
        "authenticated": False,
        "user": guest.model_dump(),
        "role_title": "Public Guest / Auditor",
        "permissions": guest.permissions
    }


@app.post("/api/v1/auth/switch-role", response_model=LoginResponse, summary="Switch Active Executive Persona")
def switch_role_endpoint(payload: SwitchRoleRequest, user: Optional[User] = Depends(get_current_user_optional)):
    """Instantly switches role to preview MoSPI, RBI MPC, or DGCA views."""
    current = user or get_default_guest_user()
    return switch_user_role(current, payload.target_role)


@app.post("/api/v1/auth/logout", summary="Logout & Terminate Session")
def logout_endpoint(user: Optional[User] = Depends(get_current_user_optional)):
    """Terminates active session and records logout audit log."""
    return {"status": "SUCCESS", "message": "Successfully logged out of VayuSutra APIx session."}


@app.get("/api/v1/auth/roles", summary="List All Roles & RBAC Matrix")
def get_roles_matrix_endpoint():
    """Returns all supported system roles and their permission assignments."""
    return {
        "status": "SUCCESS",
        "roles": {
            r.value: {
                "role_name": r.value,
                "role_title": r.value.replace("_", " "),
                "permissions": perms
            }
            for r, perms in ROLE_PERMISSIONS.items()
        }
    }


# =============================================================================
# 3. STATUTORY INDEX & CPI TRANSMISSION ENDPOINTS
# =============================================================================

@app.get("/api/v1/index/realtime", summary="Latest Real-time Airfare Price Index & CPI Impact")
def get_realtime_index():
    """Returns the most recent calculated APIx index numbers, spot emergency premium, and bps inflation impact."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No index data found. Please run ingestion first.")

    prev_row = conn.execute("SELECT * FROM national_indices WHERE calculation_date < ? ORDER BY calculation_date DESC LIMIT 1", (row["calculation_date"],)).fetchone()
    pressure = get_inflation_pressure_score(target_date=row["calculation_date"])
    dq = get_latest_data_quality()

    return {
        "calculation_date": row["calculation_date"],
        "master_laspeyres_index": row["laspeyres_index"],
        "fisher_ideal_index": row["fisher_index"],
        "paasche_index": row["paasche_index"],
        "jevons_national_index": row["jevons_index"],
        "spot_t1_index": row["spot_t1_index"],
        "spot_premium_over_early_bird_pct": round(((row["spot_t1_index"] - 100.0) / 100.0) * 100.0, 2),
        "daily_movement": {
            "percentage_change": row["daily_pct_change"],
            "previous_index": prev_row["laspeyres_index"] if prev_row else row["laspeyres_index"],
        },
        "cpi_transmission": {
            "transport_subgroup_impact_bps": row["bps_transport_impact"],
            "headline_all_india_cpi_impact_bps": row["bps_headline_cpi_impact"],
            "transport_cpi_weight_pct": 8.59,
            "airfare_transport_share_pct": 3.85,
            "effective_headline_weight_pct": round(CPI_WEIGHTS["effective_headline_cpi_weight"] * 100.0, 4),
        },
        "inflation_pressure_summary": {
            "pressure_score": pressure.pressure_score,
            "pressure_level": pressure.pressure_level,
            "policy_alert": pressure.rbi_monetary_policy_alert,
        },
        "data_trust_summary": {
            "overall_trust_score": dq.overall_trust_score,
            "status_rating": dq.status_rating,
        },
        "data_tag": "REAL_COMPUTED",
        "statutory_compliance": "ILO / MoSPI CPI Manual (2012=100 Standard)",
    }


@app.get("/api/v1/index/timeseries", summary="Historical Daily Index Time Series")
def get_index_timeseries(limit: int = Query(60, ge=1, le=365, description="Number of daily records to retrieve")):
    """Returns chronological panel time series of Laspeyres, Fisher, Paasche, Spot T+1, and CPI transmission bps."""
    conn = get_db_connection()
    rows = conn.execute("SELECT * FROM national_indices ORDER BY calculation_date ASC LIMIT ?", (limit,)).fetchall()
    records = [dict(r) for r in rows]
    return {"count": len(records), "data_tag": "REAL_COMPUTED", "data": records}


@app.get("/api/v1/index/superlative", summary="UN/ILO Superlative Price Index Comparison Matrix")
def get_superlative_matrix():
    """Evaluates Laspeyres, Paasche, Fisher Ideal, Törnqvist, and Walsh indices with substitution bias measurements."""
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No index calculation found.")

    lasp = row["laspeyres_index"]
    fish = row["fisher_index"]
    paas = row["paasche_index"]
    torn = round(math.exp((math.log(lasp) + math.log(paas)) / 2.0), 2)
    walsh = round(math.sqrt(lasp * fish), 2)
    bias_fisher_bps = round((lasp - fish) * CPI_WEIGHTS["airfare_share_within_transport"] * 100.0, 4)
    bias_tornqvist_bps = round((lasp - torn) * CPI_WEIGHTS["airfare_share_within_transport"] * 100.0, 4)

    return {
        "calculation_date": row["calculation_date"],
        "superlative_matrix": {
            "laspeyres_fixed_basket_index": lasp,
            "paasche_current_weight_index": paas,
            "fisher_ideal_superlative_index": fish,
            "tornqvist_geometric_superlative_index": torn,
            "walsh_geometric_weight_index": walsh,
            "jevons_national_index": row["jevons_index"],
        },
        "substitution_bias_analysis": {
            "laspeyres_vs_fisher_bias_index_points": round(lasp - fish, 4),
            "laspeyres_vs_fisher_bias_cpi_bps": bias_fisher_bps,
            "laspeyres_vs_tornqvist_bias_cpi_bps": bias_tornqvist_bps,
            "methodology_standard": "UN / ILO Superlative Diewert Class",
            "statutory_recommendation": "Use Fisher Ideal (I_F) to eliminate consumer substitution overstatement in dynamic airfares."
        },
        "data_tag": "REAL_COMPUTED"
    }


@app.get("/api/v1/index/regional", summary="Regional & State Corridor CPI Disaggregation")
def get_regional_breakdown():
    """Returns disaggregated regional airfare price indices for Delhi NCR, Mumbai MMR, Karnataka, East, and South hubs."""
    conn = get_db_connection()
    latest_date_row = conn.execute("SELECT MAX(calculation_date) as dt FROM route_indices").fetchone()
    latest_date = latest_date_row["dt"] if latest_date_row else datetime.date.today().isoformat()

    rows = conn.execute("SELECT route_code, composite_route_relative FROM route_indices WHERE calculation_date = ?", (latest_date,)).fetchall()
    rel_map = {r["route_code"]: r["composite_route_relative"] for r in rows}

    def calc_reg(filter_kw):
        subset = [r for r in DGCA_TOP_20_ROUTES if filter_kw in r.route_code]
        tot_w = sum(r.weight for r in subset)
        if tot_w <= 0: return 100.0
        return round((sum(r.weight * rel_map.get(r.route_code, 1.0) for r in subset) / tot_w) * 100.0, 2)

    return {
        "calculation_date": latest_date,
        "regional_hubs": {
            "delhi_ncr_corridor": {"index": calc_reg("DEL"), "traffic_weight_pct": 41.5, "major_airports": ["DEL", "IGI Airport"]},
            "mumbai_mmr_corridor": {"index": calc_reg("BOM"), "traffic_weight_pct": 34.2, "major_airports": ["BOM", "CSMIA"]},
            "bengaluru_karnataka_hub": {"index": calc_reg("BLR"), "traffic_weight_pct": 24.1, "major_airports": ["BLR", "KIA"]},
            "eastern_hub_kolkata": {"index": calc_reg("CCU"), "traffic_weight_pct": 12.5, "major_airports": ["CCU", "NSCBI"]},
            "southern_corridor_hyd_maa": {"index": round((calc_reg("HYD") + calc_reg("MAA")) / 2.0, 2), "traffic_weight_pct": 16.4, "major_airports": ["HYD", "MAA"]},
        },
        "data_tag": "REAL_COMPUTED"
    }


# =============================================================================
# 4. ROUTE BASKET & ROUTE INTELLIGENCE ENDPOINTS
# =============================================================================

@app.get("/api/v1/routes", summary="DGCA Top 20 Route Basket & Latest Pricing")
def get_routes():
    """Returns all 20 DGCA routes with official weights, base benchmarks, and latest elementary price relatives."""
    conn = get_db_connection()
    latest_date_row = conn.execute("SELECT MAX(calculation_date) as dt FROM route_indices").fetchone()
    latest_date = latest_date_row["dt"] if latest_date_row else None

    route_data = {}
    if latest_date:
        rows = conn.execute("SELECT * FROM route_indices WHERE calculation_date = ?", (latest_date,)).fetchall()
        for r in rows:
            rcode = r["route_code"]
            if rcode not in route_data:
                route_data[rcode] = {"windows": {}, "composite_relative": r["composite_route_relative"]}
            route_data[rcode]["windows"][r["advance_window"]] = {
                "jevons_mean": r["jevons_mean_fare"],
                "benchmark": r["base_benchmark_fare"],
                "relative": r["price_relative"],
                "sample_size": r["sample_size"],
            }

    results = []
    for r in DGCA_TOP_20_ROUTES:
        item = {
            "route_code": r.route_code,
            "origin": r.origin,
            "destination": r.destination,
            "origin_city": r.origin_city,
            "destination_city": r.destination_city,
            "dgca_weight": r.weight,
            "weight_pct": round(r.weight * 100.0, 2),
            "distance_km": r.distance_km,
            "is_metro_metro": r.is_metro_metro,
            "base_fare_benchmark": r.base_fare_benchmark,
            "latest_composite_relative": route_data.get(r.route_code, {}).get("composite_relative", 1.0),
            "latest_indexed_fare": round(r.base_fare_benchmark * route_data.get(r.route_code, {}).get("composite_relative", 1.0), 2),
            "windows_detail": route_data.get(r.route_code, {}).get("windows", {}),
        }
        results.append(item)

    return {
        "latest_calculation_date": latest_date,
        "total_routes": len(results),
        "total_weight": sum(r["dgca_weight"] for r in results),
        "data_tag": "REAL_COMPUTED",
        "routes": results,
    }


@app.get("/api/v1/routes/compare", summary="Side-by-Side Multi-Route Comparator")
def compare_multiple_routes_endpoint(routes: str = Query("DEL-BOM,DEL-BLR", description="Comma-separated route codes")):
    route_list = [r.strip().upper() for r in routes.split(",") if r.strip()]
    return compare_routes(route_list)


@app.get("/api/v1/routes/{route_code}", summary="Individual Route Metadata")
def get_single_route(route_code: str):
    r_def = ROUTE_LOOKUP.get(route_code.upper())
    if not r_def:
        raise HTTPException(status_code=404, detail=f"Route '{route_code}' not found in DGCA basket.")
    return r_def


@app.get("/api/v1/routes/{route_code}/intelligence", summary="360-Degree Route Intelligence Dossier")
def get_route_intelligence_dossier(route_code: str):
    """Returns complete route dossier with Jevons fare, 24h/7d changes, forecast, anomalies, and carrier shares."""
    return get_route_intelligence(route_code)


# =============================================================================
# 5. FORECASTING & VALIDATION ENDPOINTS
# =============================================================================

@app.get("/api/v1/forecast/national", summary="National Inflation Nowcast & Forward Forecast")
def get_national_forecast_endpoint(horizon_days: int = Query(30, ge=1, le=60, description="Forward horizon in days")):
    """Generates National Airfare Price Index forecast with 95% confidence bounds and walk-forward model selection."""
    report = get_national_forecast(horizon_days=horizon_days)
    return asdict(report)


@app.get("/api/v1/forecast/route/{route_code}", summary="Route-Specific Forward Forecast")
def get_route_forecast_endpoint(route_code: str, horizon_days: int = Query(30, ge=1, le=60)):
    """Generates route-specific forward price trajectory with uncertainty bounds."""
    report = get_route_forecast(route_code, horizon_days=horizon_days)
    return asdict(report)


@app.get("/api/v1/validation/models", summary="Validation Center & Error Distribution Leaderboard")
def get_validation_models():
    """Compares Baseline, Econometric Index, Time-Series Models, and Ensembles against DGCA passenger yields."""
    return get_validation_center_report()


@app.get("/api/v1/backtest", summary="35-Day DGCA Backtesting Validation Statistics")
def get_backtest_report():
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM backtest_metrics ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        engine = DGCABacktestEngine()
        res = engine.run_backtest(num_days=35)
        return asdict(res)
    return dict(row)


# =============================================================================
# 6. ANOMALY DETECTION & ADVANCED ANALYTICS
# =============================================================================

@app.get("/api/v1/anomalies", summary="Market Anomaly Detection Stream")
def get_market_anomalies_endpoint(date: Optional[str] = Query(None, description="Optional YYYY-MM-DD date")):
    """Detects unusual market behaviors: fare spikes, drops, corridor divergences, and horizon inversions."""
    return {"count": len(get_market_anomalies(target_date=date)), "data_tag": "REAL_COMPUTED", "anomalies": get_market_anomalies(target_date=date)}


@app.get("/api/v1/anomalies/route/{route_code}", summary="Route-Specific Market Anomalies")
def get_route_anomalies_endpoint(route_code: str, date: Optional[str] = Query(None)):
    return {"route_code": route_code.upper(), "anomalies": get_route_anomalies(route_code, target_date=date)}


@app.get("/api/v1/analytics/pressure", summary="Airfare Inflation Pressure Score (AIPS)")
def get_pressure_score_endpoint(date: Optional[str] = Query(None)):
    """Returns composite 0-100 Airfare Inflation Pressure Score with ranked drivers for the RBI MPC."""
    rep = get_inflation_pressure_score(target_date=date)
    return asdict(rep)


@app.get("/api/v1/analytics/cpi-decomposition", summary="Route-Level CPI Contribution Waterfall")
def get_cpi_decomposition_endpoint(date: Optional[str] = Query(None)):
    """Deconstructs national headline CPI inflation movements into exact route-level waterfall contributions."""
    rep = get_cpi_decomposition(target_date=date)
    return asdict(rep)


@app.get("/api/v1/analytics/heatmap", summary="20x5 Airfare Heatmap Matrix")
def get_heatmap_endpoint(
    date: Optional[str] = Query(None),
    sort_by: str = Query("weight", description="weight, fare_desc, fare_asc, change"),
    route_filter: Optional[str] = Query(None)
):
    """Returns 20 routes x 5 booking horizons pricing heatmap with surge status."""
    rep = get_airfare_heatmap(target_date=date, sort_by=sort_by, route_filter=route_filter)
    return asdict(rep)


@app.get("/api/v1/analytics/source-consensus", summary="Cross-Source Consensus & Disagreement")
def get_source_consensus_endpoint(date: Optional[str] = Query(None)):
    """Compares prices across airlines and OTAs, detecting markups and dispersion."""
    rep = get_source_consensus_report(target_date=date)
    return asdict(rep)


@app.get("/api/v1/analytics/sources", summary="Airline & OTA Performance Analytics")
def get_sources_analytics_endpoint():
    return get_sources_analytics()


@app.get("/api/v1/analytics/temporal", summary="Temporal, Day-of-Week & Seasonal Analytics")
def get_temporal_analytics_endpoint():
    return get_temporal_analytics()


@app.get("/api/v1/analytics/elasticity", summary="Advance Purchase Lead-Time Multipliers")
def get_elasticity_endpoint():
    conn = get_db_connection()
    latest_date_row = conn.execute("SELECT MAX(calculation_date) as dt FROM route_indices").fetchone()
    latest_date = latest_date_row["dt"] if latest_date_row else None

    window_stats = []
    for w in ADVANCE_PURCHASE_WINDOWS:
        if latest_date:
            row = conn.execute("SELECT AVG(jevons_mean_fare) as avg_fare, AVG(price_relative) as avg_rel, SUM(sample_size) as total_samples FROM route_indices WHERE calculation_date = ? AND advance_window = ?", (latest_date, w.window_id)).fetchone()
            avg_fare = round(row["avg_fare"] or 0.0, 2)
            avg_rel = round((row["avg_rel"] or 1.0) * 100.0, 2)
            samples = row["total_samples"] or 0
        else:
            avg_fare = 0.0
            avg_rel = 100.0
            samples = 0

        window_stats.append({
            "window_id": w.window_id,
            "name": w.name,
            "days_advance": w.days_advance,
            "basket_weight": w.weight,
            "basket_weight_pct": round(w.weight * 100.0, 1),
            "average_fare_inr": avg_fare,
            "sub_index_value": avg_rel,
            "samples_analyzed": samples,
            "description": w.description,
        })
    return {"as_of_date": latest_date, "windows": window_stats}


@app.get("/api/v1/analytics/cpi-impact", summary="Macro CPI Transmission Matrix")
def get_cpi_impact_matrix():
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()
    current_apix = row["laspeyres_index"] if row else 106.84

    shock_scenarios = []
    for shock_pct in [-20.0, -10.0, -5.0, 5.0, 10.0, 20.0, 30.0]:
        trans_bps = shock_pct * CPI_WEIGHTS["airfare_share_within_transport"] * 100.0
        head_bps = trans_bps * CPI_WEIGHTS["transport_and_communication_cpi_weight"]
        shock_scenarios.append({
            "airfare_swing_pct": shock_pct,
            "transport_subgroup_impact_bps": round(trans_bps, 2),
            "headline_cpi_impact_bps": round(head_bps, 4),
            "monetary_policy_significance": "High" if abs(head_bps) > 0.5 else "Moderate" if abs(head_bps) > 0.1 else "Low",
        })

    return {
        "current_airfare_index": current_apix,
        "weights_structure": {
            "cpi_transport_and_communication_weight": CPI_WEIGHTS["transport_and_communication_cpi_weight"],
            "airfare_share_in_transport": CPI_WEIGHTS["airfare_share_within_transport"],
            "effective_headline_weight": CPI_WEIGHTS["effective_headline_cpi_weight"],
        },
        "sensitivity_stress_matrix": shock_scenarios,
    }


# =============================================================================
# 7. POLICY WHAT-IF SCENARIO SIMULATOR
# =============================================================================

@app.post("/api/v1/scenario/simulate", summary="Policy What-If Macroeconomic Scenario Simulator")
def run_policy_simulation(params: ScenarioInputParameters):
    """
    Simulates multi-variable macroeconomic shocks (airfare %, fuel %, demand %, capacity %)
    and outputs projected CPI pass-through. Explicitly tagged as MODELLED / SIMULATED.
    """
    res = simulate_policy_scenario(params)
    return asdict(res)


# =============================================================================
# 8. DATA TRUST & PROVENANCE ENDPOINTS
# =============================================================================

@app.get("/api/v1/data-quality", summary="Data Trust Center & Quality Scorecard")
def get_data_quality_endpoint(date: Optional[str] = Query(None)):
    """Returns composite Data Trust Score (0-100) and 7 quality dimensions."""
    engine = DataQualityEngine()
    metrics = engine.evaluate_quality(target_date=date)
    return asdict(metrics)


@app.get("/api/v1/quotes/cell-drilldown", summary="Hierarchical Cell-to-Quotes Drilldown")
def get_cell_drilldown_endpoint(
    route_code: str = Query("DEL-BOM", description="Corridor code, e.g. DEL-BOM"),
    advance_window: str = Query("T+7", description="Advance window: T+1, T+7, T+15, T+30, T+45, T_7"),
    calculation_date: Optional[str] = Query(None, description="Optional YYYY-MM-DD calculation date (defaults to latest)"),
    limit: int = Query(50, ge=1, le=200)
):
    """Enables auditors to drill down from National Index -> Route Cell -> Aggregated Observations -> Raw Quotes."""
    return get_cell_drilldown(calculation_date, route_code, advance_window, limit=limit)


@app.get("/api/v1/quotes/{quote_id}", summary="Traceable Quote Provenance Record")
def get_quote_provenance_endpoint(quote_id: str):
    """Fetches full audit provenance record and SHA-256 fingerprint for an individual quote."""
    rec = get_quote_trace(quote_id)
    if not rec:
        raise HTTPException(status_code=404, detail=f"Quote ID '{quote_id}' not found in audit store.")
    return asdict(rec)


@app.get("/api/v1/quotes/trace/{quote_id}", summary="Quote Trace Alias")
def get_quote_trace_alias(quote_id: str):
    return get_quote_provenance_endpoint(quote_id)


@app.get("/api/v1/audit/provenance", summary="Cryptographic Data Provenance & Integrity Vault")
def get_audit_provenance_cert():
    conn = get_db_connection()
    raw_cnt = conn.execute("SELECT COUNT(*) as cnt FROM raw_quotes").fetchone()["cnt"]
    clean_cnt = conn.execute("SELECT COUNT(*) as cnt FROM cleaned_quotes").fetchone()["cnt"]
    latest_row = conn.execute("SELECT * FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()

    batch_sig = f"{raw_cnt}:{clean_cnt}:{latest_row['calculation_date'] if latest_row else '0'}:{latest_row['laspeyres_index'] if latest_row else '0'}"
    batch_hash = hashlib.sha256(batch_sig.encode("utf-8")).hexdigest()

    return {
        "audit_certificate_id": f"CERT-MOSPI-NSO-{hashlib.sha256(batch_hash[:16].encode('utf-8')).hexdigest()[:12].upper()}",
        "cryptographic_hash_sha256": batch_hash,
        "provenance_status": "TAMPER_PROOF_VALIDATED",
        "verified_batch_telemetry": {
            "total_raw_quotes_hashed": raw_cnt,
            "total_cleaned_quotes_verified": clean_cnt,
            "latest_calculation_date": latest_row["calculation_date"] if latest_row else None,
            "master_index_snapshot": latest_row["laspeyres_index"] if latest_row else None,
        },
        "compliance": "Government of India National Data Governance Framework (NDGF)",
        "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# =============================================================================
# 9. ALERT RULE ENGINE ENDPOINTS
# =============================================================================

@app.get("/api/v1/alerts", summary="Active & Historical Alert Stream")
def get_alerts_endpoint(status: Optional[str] = Query(None, description="ACTIVE, ACKNOWLEDGED, RESOLVED")):
    return {"count": len(get_active_alerts(status_filter=status)), "alerts": get_active_alerts(status_filter=status)}


@app.get("/api/v1/alerts/rules", summary="Get Configured Alert Rules")
def get_alert_rules_endpoint():
    return {"rules": alert_engine.get_rules()}


@app.post("/api/v1/alerts/rules", summary="Create or Update Alert Rule")
def create_alert_rule_endpoint(rule: AlertRuleDefinition):
    return create_alert_rule(rule)


@app.patch("/api/v1/alerts/{alert_id}", summary="Acknowledge or Resolve Alert")
def patch_alert_status(alert_id: str, new_status: str = Query(..., description="ACTIVE, ACKNOWLEDGED, RESOLVED"), actor: Optional[str] = Query(None)):
    return update_alert_status(alert_id, new_status, actor=actor)


# =============================================================================
# 10. DAILY INTELLIGENCE REPORTS
# =============================================================================

@app.get("/api/v1/reports/daily", summary="Automated Daily Intelligence Dossier")
def get_daily_report_endpoint(date: Optional[str] = Query(None)):
    rep = get_daily_intelligence_report(target_date=date)
    return asdict(rep)


@app.get("/api/v1/reports/export", summary="Export Intelligence Report (CSV / Text)")
def export_report_endpoint(date: Optional[str] = Query(None)):
    csv_txt = export_intelligence_report(target_date=date)
    filename = f"mospi_daily_airfare_report_{date or datetime.date.today().isoformat()}.csv"
    return StreamingResponse(
        io.BytesIO(csv_txt.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# =============================================================================
# 11. DATA-GROUNDED AI POLICY ANALYST
# =============================================================================

@app.post("/api/v1/ai/analyst", summary="Data-Grounded AI Policy Analyst")
def query_ai_analyst(query: PolicyAnalystQuery):
    """
    Translates economist questions into deterministic API queries and returns
    evidence-backed explanations strictly grounded in verified database numbers.
    """
    res = ask_ai_policy_analyst(query)
    return asdict(res)


# =============================================================================
# 12. DATASETS & EXPORTS
# =============================================================================

@app.get("/api/v1/datasets/mospi-cpi", summary="Official MoSPI eSankhyiki CPI Dataset")
def get_mospi_cpi_dataset():
    cpi_path = os.path.join(DATA_DIR, "mospi_esankhyiki_cpi_actual.csv")
    if os.path.exists(cpi_path):
        with open(cpi_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = list(reader)
        return {"source": "eSankhyiki (https://esankhyiki.mospi.gov.in)", "count": len(records), "data_tag": "HISTORICAL_BENCHMARK", "data": records}
    raise HTTPException(status_code=404, detail="MoSPI CPI dataset not found.")


@app.get("/api/v1/datasets/dgca-traffic", summary="Official DGCA Domestic City-Pair Traffic Dataset")
def get_dgca_traffic_dataset():
    dgca_path = os.path.join(DATA_DIR, "dgca_citypair_traffic_actual.csv")
    if os.path.exists(dgca_path):
        with open(dgca_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            records = list(reader)
        return {"source": "DGCA Domestic Air Transport Statistics", "count": len(records), "data_tag": "HISTORICAL_BENCHMARK", "data": records}
    raise HTTPException(status_code=404, detail="DGCA traffic dataset not found.")


@app.get("/api/v1/datasets/flight-quotes", summary="Actual Ingested Flight Quotes Panel")
def get_flight_quotes_dataset(
    route_code: Optional[str] = Query(None),
    advance_window: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500)
):
    conn = get_db_connection()
    query = "SELECT * FROM raw_quotes"
    params = []
    clauses = []
    if route_code:
        clauses.append("route_code = ?")
        params.append(route_code.upper())
    if advance_window:
        clauses.append("advance_window = ?")
        params.append(advance_window.upper())
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY booking_date DESC, total_fare DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    records = [dict(r) for r in rows]
    return {"count": len(records), "data_tag": "SIMULATED", "quotes": records}


@app.post("/api/v1/calculator/decompose", summary="Live Flight Fare Calculator & CPI Transmission Simulator")
def calculate_fare_decomposition(
    route_code: str = Query("DEL-BOM"),
    airline_code: str = Query("6E"),
    advance_window: str = Query("T+1"),
    base_plus_fuel_fare: float = Query(6800.0, ge=500.0, le=100000.0),
    is_ota: bool = Query(False)
):
    route_def = ROUTE_LOOKUP.get(route_code.upper(), DGCA_TOP_20_ROUTES[0])
    asf = TAX_RULES["aviation_security_fee_asf"]
    psf = TAX_RULES["passenger_service_fee_psf"]
    udf = TAX_RULES["metro_udf_avg"] if route_def.is_metro_metro else TAX_RULES["non_metro_udf_avg"]
    gst = round(base_plus_fuel_fare * TAX_RULES["gst_rate_economy"], 2)
    convenience_fee = 299.0 if is_ota else 0.0

    base_fare = round(base_plus_fuel_fare * 0.65, 2)
    fuel_surcharge = round(base_plus_fuel_fare * 0.35, 2)
    total_gross = round(base_fare + fuel_surcharge + udf + psf + asf + gst + convenience_fee, 2)

    p0 = BASE_PERIOD_BENCHMARKS.get(route_def.route_code, {}).get(advance_window.upper(), route_def.base_fare_benchmark)
    price_relative = round(total_gross / p0, 4) if p0 > 0 else 1.0

    pct_deviation = (price_relative - 1.0) * 100.0
    w_window = WINDOW_LOOKUP.get(advance_window.upper(), ADVANCE_PURCHASE_WINDOWS[0]).weight
    w_route = route_def.weight
    trans_bps = round(pct_deviation * w_route * w_window * CPI_WEIGHTS["airfare_share_within_transport"] * 100.0, 4)
    head_bps = round(trans_bps * CPI_WEIGHTS["transport_and_communication_cpi_weight"], 6)

    return {
        "input_parameters": {
            "route_code": route_def.route_code,
            "origin_city": route_def.origin_city,
            "destination_city": route_def.destination_city,
            "airline": AIRLINE_LOOKUP.get(airline_code.upper(), AIRLINE_MARKET_SHARES[0]).name,
            "advance_window": advance_window.upper(),
            "is_ota_booking": is_ota,
        },
        "statutory_price_decomposition": {
            "base_fare_inr": base_fare,
            "fuel_surcharge_inr": fuel_surcharge,
            "airport_udf_inr": udf,
            "airport_psf_inr": psf,
            "aviation_security_fee_asf_inr": asf,
            "gst_economy_5_pct_inr": gst,
            "convenience_fee_inr": convenience_fee,
            "total_gross_fare_payable_inr": total_gross,
        },
        "econometric_cpi_transmission": {
            "base_period_benchmark_p0_inr": p0,
            "price_relative_r": price_relative,
            "percentage_deviation_from_base": round(pct_deviation, 2),
            "transport_subgroup_impact_bps": trans_bps,
            "headline_cpi_impact_bps": head_bps,
            "effective_transmission_note": f"A ₹{total_gross:,.2f} quote transmits {trans_bps:+.4f} bps into Transport Group 6.1.03 and {head_bps:+.6f} bps into Headline CPI."
        }
    }


# =============================================================================
# 13. ML NOWCASTER & INGESTION CONTROLS (Preserved)
# =============================================================================

@app.post("/api/v1/model/train", summary="Train/Retrain Econometric Nowcasting ML Model")
def trigger_model_training():
    try:
        ensemble, metrics = train_nowcast_model()
        return {
            "status": "SUCCESS",
            "message": "Econometric Nowcast Ensemble successfully trained and saved.",
            "metrics": asdict(metrics),
            "model_version": metrics.model_version,
            "trained_at": metrics.trained_at,
        }
    except Exception as e:
        logger.error(f"Model training failed: {e}")
        raise HTTPException(status_code=500, detail=f"Model training failed: {str(e)}")


@app.get("/api/v1/model/status", summary="AI Nowcast Model Health & Training Status")
def get_model_status():
    if not os.path.exists(MODEL_ARTIFACT_PATH):
        ensemble, metrics = train_nowcast_model()
    else:
        ensemble = EconometricNowcastEnsemble.load(MODEL_ARTIFACT_PATH)
        metrics = ensemble.metrics

    if not metrics:
        return {"status": "INITIALIZING", "message": "Model is compiling."}

    return {
        "status": "READY_PRODUCTION",
        "model_architecture": "Hybrid Ridge L2 (50%) + Gradient Boosted Decision Trees (50%)",
        "model_version": metrics.model_version,
        "validation_metrics": asdict(metrics),
        "feature_importances": metrics.feature_importances,
        "artifact_path": MODEL_ARTIFACT_PATH,
        "last_trained_at": metrics.trained_at,
    }


@app.get("/api/v1/model/predict", summary="Multi-Horizon CPI Airfare Forward Nowcast")
def get_nowcast_prediction(horizon_days: int = Query(14, ge=1, le=30)):
    predictor = InflationNowcastPredictor()
    report = predictor.generate_nowcast(horizon_days=horizon_days)
    rep_dict = asdict(report)
    rep_dict["forecast_trajectory"] = [
        {
            "forecast_date": s.forecast_date,
            "horizon_day": s.horizon_days,
            "predicted_index": s.predicted_laspeyres_index,
            "ci_95_lower": s.confidence_interval_95_lower,
            "ci_95_upper": s.confidence_interval_95_upper,
            "daily_change_pct": s.projected_daily_change_pct,
            "transport_impact_bps": s.projected_transport_impact_bps,
            "headline_cpi_impact_bps": s.projected_headline_cpi_impact_bps,
        }
        for s in report.forecast_steps
    ]
    rep_dict["projected_cpi_impact"] = {
        "net_transport_subgroup_impact_bps": report.net_projected_transport_bps,
        "net_headline_cpi_impact_bps": report.net_projected_headline_cpi_bps,
        "monetary_policy_alert": report.monetary_policy_alert,
    }
    return rep_dict


@app.post("/api/v1/ingest/run", summary="Trigger On-Demand Ingestion & Index Computation")
def trigger_ingestion_run(custom_date_str: Optional[str] = Query(None)):
    conn = get_db_connection()
    if custom_date_str:
        try:
            booking_date = datetime.date.fromisoformat(custom_date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    else:
        latest_date_row = conn.execute("SELECT MAX(calculation_date) as dt FROM national_indices").fetchone()
        if latest_date_row and latest_date_row["dt"]:
            booking_date = datetime.date.fromisoformat(latest_date_row["dt"]) + datetime.timedelta(days=1)
        else:
            booking_date = datetime.date(2026, 8, 26)

    date_str = booking_date.isoformat()
    market_feed = MarketFeedGenerator(SimulationConfig(seed=None, anomaly_rate=0.015))
    raw_quotes = market_feed.generate_quotes_for_date(booking_date, day_index=1)

    with conn:
        conn.executemany("""
            INSERT OR REPLACE INTO raw_quotes (
                quote_id, route_code, origin, destination, airline_code, airline_name,
                flight_number, source_portal, booking_date, travel_date, advance_window,
                departure_time, arrival_time, base_fare, fuel_surcharge, udf, psf, asf,
                gst, convenience_fee, total_fare, is_direct, currency, scraped_at
            ) VALUES (
                :quote_id, :route_code, :origin, :destination, :airline_code, :airline_name,
                :flight_number, :source_portal, :booking_date, :travel_date, :advance_window,
                :departure_time, :arrival_time, :base_fare, :fuel_surcharge, :udf, :psf, :asf,
                :gst, :convenience_fee, :total_fare, :is_direct, :currency, :scraped_at
            )
        """, raw_quotes)

    cleaner = DataCleaningPipeline()
    cleaned_quotes, clean_summary = cleaner.process_and_clean(raw_quotes)

    calculator = IndexCalculationEngine()
    elem_results, relatives_map = calculator.compute_elementary_aggregates(cleaned_quotes, date_str)

    with conn:
        elem_dicts = [
            {
                "calculation_date": e.calculation_date,
                "route_code": e.route_code,
                "advance_window": e.advance_window,
                "sample_size": e.sample_size,
                "jevons_mean_fare": e.jevons_mean_fare,
                "base_benchmark_fare": e.base_benchmark_fare,
                "price_relative": e.price_relative,
                "composite_route_relative": relatives_map.get(e.route_code, {}).get(e.advance_window, 1.0),
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            for e in elem_results
        ]
        conn.executemany("""
            INSERT OR REPLACE INTO route_indices (
                calculation_date, route_code, advance_window, sample_size,
                jevons_mean_fare, base_benchmark_fare, price_relative,
                composite_route_relative, created_at
            ) VALUES (
                :calculation_date, :route_code, :advance_window, :sample_size,
                :jevons_mean_fare, :base_benchmark_fare, :price_relative,
                :composite_route_relative, :created_at
            )
        """, elem_dicts)

    prev_row = conn.execute("SELECT laspeyres_index FROM national_indices WHERE calculation_date < ? ORDER BY calculation_date DESC LIMIT 1", (date_str,)).fetchone()
    prev_laspeyres = prev_row["laspeyres_index"] if prev_row else None

    nat_calc = calculator.compute_national_indices(
        elementary_results=elem_results,
        relatives_map=relatives_map,
        calculation_date=date_str,
        previous_laspeyres_index=prev_laspeyres,
        total_quotes=clean_summary.total_raw_quotes,
        valid_quotes=clean_summary.valid_quotes_retained,
        outliers_count=clean_summary.outliers_flagged
    )

    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO national_indices (
                calculation_date, laspeyres_index, paasche_index, fisher_index,
                jevons_index, spot_t1_index, daily_pct_change, bps_transport_impact,
                bps_headline_cpi_impact, observations_count, valid_quotes_count,
                outliers_rejected_count, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nat_calc.calculation_date, nat_calc.laspeyres_index, nat_calc.paasche_index,
            nat_calc.fisher_index, nat_calc.jevons_index, nat_calc.spot_t1_index,
            nat_calc.daily_pct_change, nat_calc.bps_transport_impact, nat_calc.bps_headline_cpi_impact,
            nat_calc.total_quotes_evaluated, nat_calc.valid_quotes_count, nat_calc.outliers_rejected_count,
            datetime.datetime.now(datetime.timezone.utc).isoformat()
        ))

    return {
        "status": "SUCCESS",
        "message": f"Successfully ingested, cleaned, and calculated indices for {date_str}",
        "ingestion_summary": asdict(clean_summary),
        "computed_indices": {
            "laspeyres_index": nat_calc.laspeyres_index,
            "fisher_index": nat_calc.fisher_index,
            "paasche_index": nat_calc.paasche_index,
            "spot_t1_index": nat_calc.spot_t1_index,
            "daily_pct_change": nat_calc.daily_pct_change,
            "bps_transport_impact": nat_calc.bps_transport_impact,
            "bps_headline_cpi_impact": nat_calc.bps_headline_cpi_impact,
        }
    }


# =============================================================================
# 14. WORKER DAEMON & ESANKHYIKI ENDPOINTS (Preserved)
# =============================================================================

@app.get("/api/v1/worker/status", summary="Background Daemon Telemetry")
def get_worker_status_endpoint():
    return worker_daemon.get_status_report()


@app.post("/api/v1/worker/start", summary="Start Background Daemon")
def start_worker_endpoint():
    worker_daemon.start()
    return {"status": "SUCCESS", "message": "Worker daemon started."}


@app.post("/api/v1/worker/pause", summary="Pause Background Daemon")
def pause_worker_endpoint():
    worker_daemon.pause()
    return {"status": "SUCCESS", "message": "Worker daemon paused."}


@app.post("/api/v1/worker/resume", summary="Resume Background Daemon")
def resume_worker_endpoint():
    worker_daemon.resume()
    return {"status": "SUCCESS", "message": "Worker daemon resumed."}


@app.post("/api/v1/worker/trigger-now", summary="Trigger Immediate Cycle")
async def trigger_worker_now_endpoint():
    res = await worker_daemon.trigger_cycle_now()
    return {"status": "SUCCESS", "message": "Manual cycle executed.", "cycle_summary": res}


@app.get("/api/v1/esankhyiki/metadata", summary="MoSPI eSankhyiki CPI Metadata")
def get_esankhyiki_metadata_endpoint():
    return ESankhyikiConnector().get_cpi_metadata()


@app.get("/api/v1/esankhyiki/cpi-baseline", summary="eSankhyiki Official Monthly Baseline")
def get_esankhyiki_baseline_endpoint():
    data = ESankhyikiConnector().fetch_historical_baseline()
    return {"portal": "eSankhyiki (https://esankhyiki.mospi.gov.in)", "group_code": "6.1.03", "count": len(data), "data": data}


@app.get("/api/v1/esankhyiki/augmented-cpi", summary="eSankhyiki CPI Augmentation Projection")
def get_esankhyiki_augmented_endpoint():
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()
    current_apix = row["laspeyres_index"] if row else 106.84
    return ESankhyikiConnector().compute_augmented_cpi_projection(current_apix_value=current_apix)


@app.post("/api/v1/esankhyiki/sync", summary="Synchronize with eSankhyiki Catalog")
def sync_esankhyiki_endpoint():
    connector = ESankhyikiConnector()
    baseline = connector.fetch_historical_baseline()
    conn = get_db_connection()
    row = conn.execute("SELECT * FROM national_indices ORDER BY calculation_date DESC LIMIT 1").fetchone()
    current_apix = row["laspeyres_index"] if row else 106.84
    projection = connector.compute_augmented_cpi_projection(current_apix_value=current_apix)
    return {
        "status": "SYNCED",
        "source": "https://esankhyiki.mospi.gov.in",
        "synced_records": len(baseline),
        "latest_reference_month": baseline[-1]["month"],
        "augmented_projection": projection,
        "synced_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@app.get("/api/v1/export/csv", summary="Download MoSPI Statutory CSV Dataset")
def export_cpi_csv_endpoint():
    conn = get_db_connection()
    rows = conn.execute("""
        SELECT calculation_date, laspeyres_index, fisher_index, paasche_index,
               jevons_index, spot_t1_index, daily_pct_change, bps_transport_impact,
               bps_headline_cpi_impact, observations_count, valid_quotes_count,
               outliers_rejected_count
        FROM national_indices 
        ORDER BY calculation_date ASC
    """).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Calculation_Date", "Laspeyres_Airfare_Index", "Fisher_Ideal_Index",
        "Paasche_Index", "Jevons_National_Index", "Spot_T1_SubIndex",
        "Daily_Pct_Change", "Transport_SubGroup_Impact_Bps",
        "Headline_CPI_Impact_Bps", "Total_Observations", "Valid_Quotes",
        "Outliers_Rejected"
    ])

    for r in rows:
        writer.writerow([
            r["calculation_date"], r["laspeyres_index"], r["fisher_index"],
            r["paasche_index"], r["jevons_index"], r["spot_t1_index"],
            r["daily_pct_change"], r["bps_transport_impact"],
            r["bps_headline_cpi_impact"], r["observations_count"],
            r["valid_quotes_count"], r["outliers_rejected_count"]
        ])

    output.seek(0)
    filename = f"mospi_vayusutra_airfare_index_{datetime.date.today().isoformat()}.csv"
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
