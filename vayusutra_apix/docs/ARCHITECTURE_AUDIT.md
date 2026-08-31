# VAYUSUTRA APIx — ARCHITECTURAL AUDIT & UPGRADE BLUEPRINT
**Project:** VayuSutra APIx: National Airfare Intelligence & Inflation Decision Platform  
**Problem Statement:** Smart India Hackathon 2026 (SIH26056)  
**Beneficiaries:** Ministry of Statistics and Programme Implementation (MoSPI / NSO), Reserve Bank of India (RBI) Monetary Policy Committee, Directorate General of Civil Aviation (DGCA)  
**Date of Audit:** August 2026

---

## A. Current Architecture Overview

The existing VayuSutra APIx codebase is a Python 3.12+ / FastAPI platform built with an SQLite database operating in Write-Ahead Logging (WAL) mode. It models high-frequency domestic airfare collection, statutory index calculation, machine learning nowcasting, background task execution, and interactive dashboard rendering.

### High-Level Existing Component Graph:
```
[Scrapers / Market Feed] ──► [Cleaner & MAD Outliers] ──► [SQLite WAL DB]
                                                                │
   ┌────────────────────────────────────────────────────────────┴──────────────────────────────┐
   ▼                                                            ▼                              ▼
[Econometric Index Engine]                          [ML Nowcast Ensemble]           [eSankhyiki Connector]
(Jevons, Laspeyres, Fisher, Paasche, Törnqvist)      (15 signals: Ridge + GBDT)      (MoSPI Catalog Grp 6.1.03)
   │                                                            │                              │
   └────────────────────────────────────────────────────────────┼──────────────────────────────┘
                                                                ▼
                                                    [FastAPI Endpoints & Stream]
                                                    (REST API, WebSockets, Prometheus)
                                                                ▼
                                                    [Interactive Dashboard UI]
```

---

## B. Existing Features

1. **DGCA Top 20 Route Basket:** Defined with strict normalization summing to `1.0000` (100.00% volume weight) across 20 domestic city-pairs.
2. **5 Advance Purchase Horizons:** $T+1$ (Spot, 22%), $T+7$ (Urgent Business, 34%), $T+15$ (Planned, 24%), $T+30$ (Leisure, 14%), $T+45$ (Early Bird, 6%) with empirical multipliers.
3. **Statutory Tax Breakdown:** Standard 65/35 base-fare/fuel-surcharge split, 5% economy GST, and airport fee decomposition (UDF ₹420/₹260, PSF ₹91, ASF ₹200).
4. **Ethical Ingestion Base:** Token-Bucket rate limiter capped at 1.5 req/s with 50–180ms jitter, `robots.txt` compliance checker, and user-agent rotator.
5. **Data Cleaning Pipeline:** Multi-OTA deduplication preferring direct airline quotes over OTA clones, and Median Absolute Deviation (MAD) modified Z-score ($|M_i| > 3.0$) outlier filtering.
6. **Econometric Engine:**
   - Jevons geometric mean for elementary cells.
   - Fixed-basket Laspeyres Index ($I_L$).
   - Current-expenditure Paasche Index ($I_P$) with demand elasticity ($\epsilon = -0.85$).
   - Superlative Fisher Ideal Index ($I_F = \sqrt{I_L \cdot I_P}$).
   - Superlative Törnqvist and Walsh geometric weight indices.
   - Real-time Basis Point ($\Delta \text{Bps}$) transmission into Transport (8.59%) and Headline CPI.
7. **35-Day DGCA Backtesting Engine:** Statistical correlation ($r = 0.9858$, $\text{MAPE} = 0.838\%$, $R^2 = 0.9709$) against official DGCA passenger yields across >31,500 observations.
8. **AI/ML Nowcasting Model:** 15-signal hybrid Ridge + GBDT ensemble predicting 14-day forward indices with 95% confidence bounds.
9. **Microservices & Telemetry:** Background 60-second autonomous worker daemon, Prometheus OpenMetrics endpoint (`/metrics`), WebSocket live streaming broker (`/ws/live-feed`), and eSankhyiki sync adapter.
10. **Interactive Zero-CDN Dashboard:** Multi-theme dashboard with live flight radar, route decomposer, and scenario stress testing controls.

---

## C. Existing API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Responsive Executive Dashboard UI |
| `GET` | `/metrics` | Prometheus OpenMetrics Telemetry Stream |
| `WS` | `/ws/live-feed` | Real-Time WebSocket Streaming Broker |
| `GET` | `/api/v1/health` | System Health & Table Observation Counts |
| `GET` | `/api/v1/index/realtime` | Latest Master Laspeyres, Fisher Ideal, Spot $T+1$, and CPI $\Delta\text{Bps}$ |
| `GET` | `/api/v1/index/timeseries` | Chronological Daily Time Series |
| `GET` | `/api/v1/index/superlative` | UN/ILO Superlative Index Comparison Matrix |
| `GET` | `/api/v1/index/regional` | Regional Corridor Disaggregation (Delhi NCR, Mumbai MMR, etc.) |
| `GET` | `/api/v1/routes` | Top 20 DGCA Corridors, Volume Weights, and Base Benchmarks |
| `GET` | `/api/v1/analytics/elasticity` | Advance Purchase Lead-Time Yield Curves ($T+1$ to $T+45$) |
| `GET` | `/api/v1/analytics/cpi-impact` | Sensitivity Shock Matrix & CPI Transmission Rates |
| `GET` | `/api/v1/backtest` | 35-Day DGCA Backtest Validation Statistics |
| `POST`| `/api/v1/calculator/decompose` | Interactive Fare Decomposer & Real-Time CPI $\Delta\text{Bps}$ Calculation |
| `GET` | `/api/v1/datasets/mospi-cpi` | Official Monthly Published MoSPI eSankhyiki CPI Dataset |
| `GET` | `/api/v1/datasets/dgca-traffic` | Official DGCA Domestic City-Pair Traffic Dataset |
| `GET` | `/api/v1/datasets/flight-quotes` | Live Ingested Flight Quotes Panel with Corridor & Window Filtering |
| `GET` | `/api/v1/audit/provenance` | SHA-256 Cryptographic Audit Provenance Certificate |
| `POST`| `/api/v1/model/train` | Online Retraining of Ridge + GBDT Nowcasting Ensemble |
| `GET` | `/api/v1/model/status` | Active ML Model Validation Scores & Feature Importances |
| `GET` | `/api/v1/model/predict` | Multi-Horizon Forward Inflation Nowcast with 95% CI |
| `POST`| `/api/v1/ingest/run` | On-Demand Ingestion Cycle Trigger |
| `GET` | `/api/v1/worker/status` | Background Daemon Status & Execution Metrics |
| `POST`| `/api/v1/worker/start` | Start Background Worker |
| `POST`| `/api/v1/worker/pause` | Pause Background Worker |
| `POST`| `/api/v1/worker/resume` | Resume Background Worker |
| `POST`| `/api/v1/worker/trigger-now` | Trigger Immediate Worker Cycle |
| `GET` | `/api/v1/esankhyiki/metadata` | MoSPI eSankhyiki Group 6.1.03 Classification Codes |
| `GET` | `/api/v1/esankhyiki/cpi-baseline` | Official Published Transport & Headline CPI Series |
| `GET` | `/api/v1/esankhyiki/augmented-cpi` | Real-Time Transmission Nowcast into eSankhyiki Baseline |
| `POST`| `/api/v1/esankhyiki/sync` | Synchronize Catalogs with `esankhyiki.mospi.gov.in` |
| `GET` | `/api/v1/export/csv` | Downloadable MoSPI-Formatted CSV Dataset |

---

## D. Existing Data Flow

1. **Ingestion:** Scrapers / Market Feed produce raw quote dictionaries $\rightarrow$ persisted into `raw_quotes` table.
2. **Scrubbing:** `DataCleaningPipeline` validates Pydantic schemas $\rightarrow$ runs multi-OTA deduplication $\rightarrow$ runs stratified MAD outlier detection $\rightarrow$ decomposes statutory taxes $\rightarrow$ persists into `cleaned_quotes` table.
3. **Elementary Calculation:** `IndexCalculationEngine` aggregates valid quotes by `(route_code, advance_window)` using Jevons geometric mean $\rightarrow$ calculates price relatives $R_{r,k}^t = \bar{P}_{r,k}^t / P_{r,k}^0 \rightarrow$ persists into `route_indices` table.
4. **Higher-Level Compilation:** `IndexCalculationEngine` computes route composite relatives $\bar{R}_r^t$, compiles Laspeyres ($I_L$), Paasche ($I_P$), Fisher ($I_F$), Törnqvist, and Walsh indices $\rightarrow$ computes CPI $\Delta \text{Bps}$ transmission $\rightarrow$ persists into `national_indices` table.
5. **Broadcasting & Telemetry:** `worker_daemon` updates Prometheus gauges and broadcasts JSON payload via `stream_manager` WebSocket broker to connected clients.
6. **Nowcasting:** `InflationNowcastPredictor` rolls forward autoregressively to compute 14-day projections with 95% confidence bands.

---

## E. Existing Database Schema

* `raw_quotes`: `(quote_id PRIMARY KEY, route_code, origin, destination, airline_code, airline_name, flight_number, source_portal, booking_date, travel_date, advance_window, departure_time, arrival_time, base_fare, fuel_surcharge, udf, psf, asf, gst, convenience_fee, total_fare, is_direct, currency, scraped_at)`
* `cleaned_quotes`: `(cleaned_id PRIMARY KEY, raw_quote_id, route_code, advance_window, booking_date, travel_date, airline_code, flight_number, final_base_fare, final_tax_fee, final_total_fare, outlier_flag, outlier_reason, deduplication_kept, cleaned_at)`
* `route_indices`: `(id PRIMARY KEY, calculation_date, route_code, advance_window, sample_size, jevons_mean_fare, base_benchmark_fare, price_relative, composite_route_relative, created_at)`
* `national_indices`: `(id PRIMARY KEY, calculation_date UNIQUE, laspeyres_index, paasche_index, fisher_index, jevons_index, spot_t1_index, daily_pct_change, bps_transport_impact, bps_headline_cpi_impact, observations_count, valid_quotes_count, outliers_rejected_count, created_at)`
* `backtest_metrics`: `(id PRIMARY KEY, metric_date, pearson_r, mape, rmse, r2, sample_days, total_quotes_evaluated, report_path, generated_at)`

---

## F. Existing Mathematical Formulas

1. **Jevons Geometric Mean:** $\bar{P}_{r,k}^t = \left(\prod_{i=1}^n p_{r,k,i}^t\right)^{1/n} = \exp\left(\frac{1}{n}\sum \ln(p_i)\right)$
2. **Laspeyres Basket Index:** $I_L^t = \left(\sum w_r^0 \bar{R}_r^t\right) \times 100$
3. **Paasche Index:** $I_P^t = \frac{\sum w_r^0 (\bar{R}_r^t)^{1+\epsilon}}{\sum w_r^0 (\bar{R}_r^t)^\epsilon} \times 100 \quad (\epsilon = -0.85)$
4. **Fisher Ideal Index:** $I_F^t = \sqrt{I_L^t \cdot I_P^t}$
5. **Törnqvist Index:** $I_T^t = \exp\left(\sum \frac{w_r^0 + w_r^t}{2} \ln(\bar{R}_r^t)\right) \times 100$
6. **Walsh Index:** $I_W^t = \frac{\sum \sqrt{w_r^0 w_r^t} \bar{R}_r^t}{\sum \sqrt{w_r^0 w_r^t}} \times 100$
7. **CPI Transmission:** $\Delta \text{Bps}_{\text{Transport}} = \Delta\% \times 3.85\% \times 100$, $\Delta \text{Bps}_{\text{Headline}} = \Delta \text{Bps}_{\text{Transport}} \times 8.59\%$
8. **MAD Modified Z-Score:** $M_i = \frac{0.6745(x_i - \text{median})}{\text{MAD}}$

---

## G. Existing Test Coverage

The test suite contains **37 unit and integration tests** in `vayusutra_apix/tests/`:
- `test_rate_limiter.py`: 5 tests (token bucket timing, capacity, jitter, user-agent headers, robots fallback).
- `test_cleaner.py`: 3 tests (MAD filter on extreme values, multi-OTA deduplication, full cleaning pipeline).
- `test_index_math.py`: 4 tests (analytical Jevons, Laspeyres/Fisher, CPI bps transmission, Paasche elasticity).
- `test_model_trainer.py`: 4 tests (feature matrix generation, model training & serialization, prediction confidence intervals, ML endpoints).
- `test_esankhyiki.py`: 4 tests (metadata, baseline fetching, augmented projection, sync endpoint).
- `test_service.py`: 4 tests (Prometheus metrics, worker daemon controls, WebSockets, CLI invocation).
- `test_api.py`: 13 tests (dashboard, health, realtime, timeseries, routes, elasticity, CPI impact, backtest, ingest run, CSV export, actual datasets, live calculator, superlative/regional/provenance).

---

## H. Technical Debt & Gaps

1. **Monolithic API Structure:** All endpoint handlers are currently in a single `main.py` file (~990 lines) rather than structured sub-routers (`api/routes/`).
2. **Forecasting Model Selection:** Current nowcaster uses a fixed ensemble without multi-model comparison (e.g. Seasonal Naive, Exponential Smoothing/ETS, SARIMA vs GBDT) and lacks automated model selection based on walk-forward validation.
3. **Market Anomaly vs Data Quality Separation:** Market anomalies (e.g., airline fare wars, booking horizon inversions, corridor divergence) should be distinguished from data quality glitches (e.g. scrape errors, bad formats).
4. **Data Quality & Trust Scoring:** Needs a composite **Data Trust Score (0–100)** evaluating freshness, completeness, route coverage, source health, duplicate rates, and consensus.
5. **CPI Contribution Decomposition:** Current CPI impact provides aggregate figures but needs route-level waterfall attribution (`DEL-BOM +2.41 bps`, `DEL-BLR +1.92 bps`, etc.).
6. **Policy What-If Simulator:** Needs a multi-variable scenario engine (airfare shock %, demand %, capacity %, fuel adjustment) with modeled output tags.
7. **Role-Based Perspectives:** Dashboard needs 3 dedicated view modes: **Policy Mode**, **Analyst Mode**, and **Aviation Mode**.
8. **Alert Rule Engine:** Needs persistence and rule configuration for automated alerts (threshold spikes, CPI impact, data quality drops).
9. **Automated Intelligence Reports:** Needs daily automated intelligence report generation (JSON, CSV, downloadable executive summary).
10. **Data-Grounded AI Policy Analyst:** Needs a verified query engine that grounds answers strictly in API statistics with zero hallucination.

---

## I. Recommended Upgrade Roadmap

Following the sequence:
$$\textbf{Data Trust} \longrightarrow \textbf{Forecast} \longrightarrow \textbf{Explain} \longrightarrow \textbf{Simulate} \longrightarrow \textbf{AI Assistant}$$

1. **Phase 1: Foundation & Data Trust**
   - Refactor `config/db.py` to add normalized tables (`quotes`, `sources`, `forecasts`, `anomalies`, `alerts`, `scenario_runs`, `data_quality_snapshots`, `audit_events`).
   - Implement `data_quality/` and Data Trust Score (0–100) with `GET /api/v1/data-quality`.
   - Implement Data Provenance & Drill-down (`GET /api/v1/quotes/{quote_id}`).
   - Implement Source Consensus & Disagreement analysis (`GET /api/v1/analytics/source-consensus`).

2. **Phase 2: Forecasting & Market Anomalies**
   - Implement `forecasting/` framework with Seasonal Naive, Holt-Winters/ETS, SARIMA, GBDT, and Ensemble with walk-forward validation (MAE, RMSE, MAPE, sMAPE, $R^2$).
   - Implement `anomaly/` market anomaly detection (rolling z-score, EWMA, horizon inversion, source disagreement).
   - Implement `analytics/pressure` composite Airfare Inflation Pressure Score (0–100).

3. **Phase 3: Explanation, Decomposition & Simulation**
   - Implement `analytics/cpi-decomposition` route-level waterfall attribution.
   - Implement `analytics/heatmap` (20 routes $\times$ 5 horizons interactive matrix).
   - Implement `scenario/` Policy What-If Simulator (`POST /api/v1/scenario/simulate`).
   - Implement `alerts/` rule engine (`POST /api/v1/alerts/rules`, `GET /api/v1/alerts`).

4. **Phase 4: Reports, AI Analyst & Multi-Role UI**
   - Implement `reports/` automated daily intelligence report generator.
   - Implement `ai_analyst/` verified data-grounded policy analyst (`POST /api/v1/ai/analyst`).
   - Implement `validation/` model validation center (`GET /api/v1/validation/models`).
   - Upgrade Dashboard UI with 3 Role Modes (Policy, Analyst, Aviation), interactive India Route Map, and bento views.

5. **Phase 5: Performance, Hardening & Documentation**
   - Add Request ID and structured logging middleware.
   - Add in-process caching for high-frequency queries.
   - Add unit and integration tests for every new module.
   - Update `docs/UPGRADE_REPORT.md` and `README.md`.
