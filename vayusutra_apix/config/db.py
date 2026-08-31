"""
VayuSutra APIx - High-Performance SQLite WAL Database Layer
Thread-safe connection pooling, normalized schema migrations, indexing, and batch operations.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Generator, List, Dict, Any, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DEFAULT_DB_PATH = os.path.join(DATA_DIR, "vayusutra_airfare.db")


def get_resolved_db_path() -> str:
    """Resolves database file path with automatic /tmp fallback for Vercel/Serverless environments."""
    env_path = os.getenv("DATABASE_PATH")
    if env_path:
        return env_path

    # Check for Vercel or Serverless Lambda container
    if os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        tmp_db = "/tmp/vayusutra_airfare.db"
        if os.path.exists(DEFAULT_DB_PATH) and not os.path.exists(tmp_db):
            import shutil
            try:
                shutil.copy2(DEFAULT_DB_PATH, tmp_db)
            except Exception:
                pass
        return tmp_db

    return DEFAULT_DB_PATH


DB_PATH = get_resolved_db_path()

_thread_local = threading.local()


class DatabaseManager:
    """Manages SQLite WAL-mode connections with proper concurrency, indexing, and pragma settings."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        """Get or create a thread-local SQLite connection."""
        if not hasattr(_thread_local, "connection") or _thread_local.connection is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
            )
            conn.row_factory = sqlite3.Row
            # Enable WAL mode and performance pragmas
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("PRAGMA busy_timeout=10000;")
            conn.execute("PRAGMA cache_size=-64000;")  # 64MB memory cache
            _thread_local.connection = conn
        return _thread_local.connection

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for atomic transaction block."""
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def init_db(self) -> None:
        """Initialize and migrate database schema with normalized tables and indexes."""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            cursor = conn.cursor()

            # -------------------------------------------------------------
            # 1. CORE QUOTE TABLES (Preserved for full backward compatibility)
            # -------------------------------------------------------------
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS raw_quotes (
                    quote_id TEXT PRIMARY KEY,
                    route_code TEXT NOT NULL,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    airline_code TEXT NOT NULL,
                    airline_name TEXT NOT NULL,
                    flight_number TEXT NOT NULL,
                    source_portal TEXT NOT NULL,
                    booking_date TEXT NOT NULL,
                    travel_date TEXT NOT NULL,
                    advance_window TEXT NOT NULL,
                    departure_time TEXT NOT NULL,
                    arrival_time TEXT NOT NULL,
                    base_fare REAL NOT NULL,
                    fuel_surcharge REAL NOT NULL,
                    udf REAL NOT NULL,
                    psf REAL NOT NULL,
                    asf REAL NOT NULL,
                    gst REAL NOT NULL,
                    convenience_fee REAL NOT NULL,
                    total_fare REAL NOT NULL,
                    is_direct INTEGER NOT NULL DEFAULT 1,
                    currency TEXT NOT NULL DEFAULT 'INR',
                    scraped_at TEXT NOT NULL
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_raw_route_date_win 
                ON raw_quotes(route_code, booking_date, advance_window);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_raw_flight_travel 
                ON raw_quotes(flight_number, travel_date);
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cleaned_quotes (
                    cleaned_id TEXT PRIMARY KEY,
                    raw_quote_id TEXT NOT NULL,
                    route_code TEXT NOT NULL,
                    advance_window TEXT NOT NULL,
                    booking_date TEXT NOT NULL,
                    travel_date TEXT NOT NULL,
                    airline_code TEXT NOT NULL,
                    flight_number TEXT NOT NULL,
                    final_base_fare REAL NOT NULL,
                    final_tax_fee REAL NOT NULL,
                    final_total_fare REAL NOT NULL,
                    outlier_flag INTEGER NOT NULL DEFAULT 0,
                    outlier_reason TEXT,
                    deduplication_kept INTEGER NOT NULL DEFAULT 1,
                    cleaned_at TEXT NOT NULL,
                    FOREIGN KEY (raw_quote_id) REFERENCES raw_quotes(quote_id)
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cleaned_route_win_date 
                ON cleaned_quotes(route_code, advance_window, booking_date, outlier_flag);
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS route_indices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calculation_date TEXT NOT NULL,
                    route_code TEXT NOT NULL,
                    advance_window TEXT NOT NULL,
                    sample_size INTEGER NOT NULL,
                    jevons_mean_fare REAL NOT NULL,
                    base_benchmark_fare REAL NOT NULL,
                    price_relative REAL NOT NULL,
                    composite_route_relative REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(calculation_date, route_code, advance_window)
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_route_calc_date 
                ON route_indices(calculation_date, route_code);
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS national_indices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    calculation_date TEXT UNIQUE NOT NULL,
                    laspeyres_index REAL NOT NULL,
                    paasche_index REAL NOT NULL,
                    fisher_index REAL NOT NULL,
                    jevons_index REAL NOT NULL,
                    spot_t1_index REAL NOT NULL,
                    daily_pct_change REAL NOT NULL,
                    bps_transport_impact REAL NOT NULL,
                    bps_headline_cpi_impact REAL NOT NULL,
                    observations_count INTEGER NOT NULL,
                    valid_quotes_count INTEGER NOT NULL,
                    outliers_rejected_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_national_calc_date 
                ON national_indices(calculation_date);
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backtest_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_date TEXT NOT NULL,
                    pearson_r REAL NOT NULL,
                    mape REAL NOT NULL,
                    rmse REAL NOT NULL,
                    r2 REAL NOT NULL,
                    sample_days INTEGER NOT NULL,
                    total_quotes_evaluated INTEGER NOT NULL,
                    report_path TEXT NOT NULL,
                    generated_at TEXT NOT NULL
                );
            """)

            # -------------------------------------------------------------
            # 2. NORMALIZED PRODUCTION EXTENSIONS
            # -------------------------------------------------------------
            # Sources catalog & health
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    last_scraped_at TEXT,
                    success_rate_24h REAL NOT NULL DEFAULT 100.0,
                    avg_latency_ms REAL NOT NULL DEFAULT 45.0,
                    error_count_24h INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
            """)

            # Normalized Routes Registry
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS routes_registry (
                    route_code TEXT PRIMARY KEY,
                    origin TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    origin_city TEXT NOT NULL,
                    destination_city TEXT NOT NULL,
                    dgca_weight REAL NOT NULL,
                    distance_km INTEGER NOT NULL,
                    is_metro_metro INTEGER NOT NULL,
                    base_benchmark_fare REAL NOT NULL,
                    active_carriers_count INTEGER NOT NULL DEFAULT 5,
                    created_at TEXT NOT NULL
                );
            """)

            # Forecast store with confidence intervals
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS forecasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    forecast_date TEXT NOT NULL,
                    target_date TEXT NOT NULL,
                    target_type TEXT NOT NULL DEFAULT 'NATIONAL',
                    target_code TEXT NOT NULL DEFAULT 'NATIONAL',
                    horizon_days INTEGER NOT NULL,
                    forecast_value REAL NOT NULL,
                    lower_bound_95 REAL NOT NULL,
                    upper_bound_95 REAL NOT NULL,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    mae REAL,
                    rmse REAL,
                    mape REAL,
                    data_tag TEXT NOT NULL DEFAULT 'MODELLED',
                    generated_at TEXT NOT NULL
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_forecasts_target 
                ON forecasts(forecast_date, target_code, horizon_days);
            """)

            # Market Anomalies store
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS market_anomalies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    route_code TEXT NOT NULL,
                    anomaly_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    observed_value REAL NOT NULL,
                    expected_range_min REAL NOT NULL,
                    expected_range_max REAL NOT NULL,
                    deviation_pct REAL NOT NULL,
                    confidence REAL NOT NULL,
                    explanation TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'DETECTED',
                    created_at TEXT NOT NULL
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_anomalies_route_date 
                ON market_anomalies(route_code, timestamp);
            """)

            # Alert Rules
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alert_rules (
                    rule_id TEXT PRIMARY KEY,
                    rule_name TEXT NOT NULL,
                    metric_target TEXT NOT NULL,
                    condition_operator TEXT NOT NULL,
                    threshold_value REAL NOT NULL,
                    severity TEXT NOT NULL,
                    is_enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
            """)

            # Triggered Alerts Log
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    rule_id TEXT,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    triggered_at TEXT NOT NULL,
                    resolved_at TEXT,
                    acknowledged_by TEXT
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_alerts_status 
                ON alerts(status, triggered_at);
            """)

            # Scenario Simulations
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scenario_runs (
                    run_id TEXT PRIMARY KEY,
                    scenario_name TEXT NOT NULL,
                    airfare_shock_pct REAL NOT NULL,
                    demand_change_pct REAL NOT NULL,
                    capacity_change_pct REAL NOT NULL,
                    atf_fuel_shock_pct REAL NOT NULL,
                    projected_airfare_index REAL NOT NULL,
                    projected_transport_cpi_bps REAL NOT NULL,
                    projected_headline_cpi_bps REAL NOT NULL,
                    projected_pressure_level TEXT NOT NULL,
                    data_tag TEXT NOT NULL DEFAULT 'MODELLED',
                    executed_at TEXT NOT NULL
                );
            """)

            # Data Quality Snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS data_quality_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_date TEXT UNIQUE NOT NULL,
                    overall_trust_score REAL NOT NULL,
                    freshness_pct REAL NOT NULL,
                    completeness_pct REAL NOT NULL,
                    route_coverage_pct REAL NOT NULL,
                    source_health_pct REAL NOT NULL,
                    duplicate_rate_pct REAL NOT NULL,
                    outlier_rate_pct REAL NOT NULL,
                    validation_success_pct REAL NOT NULL,
                    consensus_score REAL NOT NULL,
                    status_rating TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

            # Audit Events Ledger (Provenance)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor TEXT NOT NULL DEFAULT 'SYSTEM',
                    sha256_hash TEXT NOT NULL,
                    details_json TEXT
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_audit_entity 
                ON audit_events(entity_type, entity_id);
            """)

            # Seed default alert rules if none exist
            cursor.execute("SELECT COUNT(*) as cnt FROM alert_rules")
            if cursor.fetchone()[0] == 0:
                default_rules = [
                    ("RULE-01", "Severe Airfare Daily Spike", "daily_pct_change", ">", 5.0, "HIGH", 1, "2026-08-01T00:00:00Z"),
                    ("RULE-02", "Critical CPI Transport Surge", "bps_transport_impact", ">", 20.0, "CRITICAL", 1, "2026-08-01T00:00:00Z"),
                    ("RULE-03", "Airfare Inflation Pressure High", "pressure_score", ">", 75.0, "HIGH", 1, "2026-08-01T00:00:00Z"),
                    ("RULE-04", "Data Quality Trust Score Degraded", "overall_trust_score", "<", 80.0, "MEDIUM", 1, "2026-08-01T00:00:00Z"),
                    ("RULE-05", "Extreme Market Anomaly Detected", "anomaly_severity", "==", 4.0, "CRITICAL", 1, "2026-08-01T00:00:00Z"),
                ]
                cursor.executemany("""
                    INSERT INTO alert_rules (rule_id, rule_name, metric_target, condition_operator, threshold_value, severity, is_enabled, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, default_rules)

            # Seed sources registry
            cursor.execute("SELECT COUNT(*) as cnt FROM sources")
            if cursor.fetchone()[0] == 0:
                default_sources = [
                    ("SRC-6E", "IndiGo Direct", "AIRLINE_DIRECT", "https://www.goindigo.in", "ACTIVE", "2026-08-26T00:00:00Z", 99.4, 42.0, 0, 1, "2026-08-01T00:00:00Z"),
                    ("SRC-AI", "Air India Direct", "AIRLINE_DIRECT", "https://www.airindia.com", "ACTIVE", "2026-08-26T00:00:00Z", 98.8, 55.0, 1, 1, "2026-08-01T00:00:00Z"),
                    ("SRC-QP", "Akasa Air Direct", "AIRLINE_DIRECT", "https://www.akasaair.com", "ACTIVE", "2026-08-26T00:00:00Z", 99.1, 38.0, 0, 1, "2026-08-01T00:00:00Z"),
                    ("SRC-SG", "SpiceJet Direct", "AIRLINE_DIRECT", "https://www.spicejet.com", "ACTIVE", "2026-08-26T00:00:00Z", 97.5, 62.0, 2, 1, "2026-08-01T00:00:00Z"),
                    ("SRC-MMT", "MakeMyTrip OTA", "OTA_AGGREGATOR", "https://www.makemytrip.com", "ACTIVE", "2026-08-26T00:00:00Z", 99.0, 48.0, 0, 1, "2026-08-01T00:00:00Z"),
                    ("SRC-EMT", "EaseMyTrip OTA", "OTA_AGGREGATOR", "https://www.easemytrip.com", "ACTIVE", "2026-08-26T00:00:00Z", 98.9, 44.0, 0, 1, "2026-08-01T00:00:00Z"),
                    ("SRC-CT", "Cleartrip OTA", "OTA_AGGREGATOR", "https://www.cleartrip.com", "ACTIVE", "2026-08-26T00:00:00Z", 98.2, 51.0, 1, 1, "2026-08-01T00:00:00Z"),
                    ("SRC-ESANKHYIKI", "MoSPI eSankhyiki", "GOVERNMENT_PORTAL", "https://esankhyiki.mospi.gov.in", "ACTIVE", "2026-08-26T00:00:00Z", 100.0, 30.0, 0, 1, "2026-08-01T00:00:00Z"),
                ]
                cursor.executemany("""
                    INSERT INTO sources (source_id, source_name, source_type, base_url, status, last_scraped_at, success_rate_24h, avg_latency_ms, error_count_24h, is_active, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, default_sources)

            conn.commit()
            conn.close()


# Global instance
db_manager = DatabaseManager()


def get_db_connection() -> sqlite3.Connection:
    """Convenience helper to get current thread's connection."""
    return db_manager.get_connection()


def init_db(db_path: str = DB_PATH) -> None:
    """Explicitly initialize schema."""
    global db_manager
    db_manager = DatabaseManager(db_path)
