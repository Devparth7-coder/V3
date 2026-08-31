#!/usr/bin/env bash
# ==============================================================================
# VayuSutra APIx - One-Click Production Deployment Script
# Ministry of Statistics and Programme Implementation (MoSPI) / RBI / DGCA
# ==============================================================================

set -eo pipefail

echo "========================================================================"
echo "    VAYUSUTRA APIx - NATIONAL AIRFARE INTELLIGENCE PLATFORM (SIH26056)   "
echo "                   PRODUCTION DEPLOYMENT ORCHESTRATOR                  "
echo "========================================================================"

# Check Python environment
if ! command -v python3 &> /dev/null; then
    echo "[-] Error: python3 is not installed."
    exit 1
fi

echo "[*] Step 1/5: Checking Python & Environment Requirements..."
PYTHON_VER=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
echo "    -> Detected Python version: $PYTHON_VER"

if [ ! -f ".env" ]; then
    echo "[*] Creating .env from .env.example template..."
    cp .env.example .env
fi

echo "[*] Step 2/5: Installing Production Dependencies..."
python3 -m pip install -q --upgrade pip
python3 -m pip install -q -r requirements.txt

echo "[*] Step 3/5: Initializing Database & Pre-Seeding RBAC Users..."
python3 -c "
from vayusutra_apix.config.db import init_db
from vayusutra_apix.auth import init_auth_tables
init_db()
init_auth_tables()
print('    -> Database and RBAC tables initialized successfully.')
"

echo "[*] Step 4/5: Running Test Suite Validation Matrix..."
if command -v pytest &> /dev/null; then
    pytest -q --tb=short
    echo "    -> All unit & integration tests passed with 100% success."
else
    echo "    -> pytest not found, skipping local test run."
fi

echo "[*] Step 5/5: Starting Production Service..."
echo "========================================================================"
echo "    Service running at: http://0.0.0.0:8000"
echo "    API Documentation: http://0.0.0.0:8000/docs"
echo "    Prometheus Stream : http://0.0.0.0:8000/metrics"
echo "========================================================================"

exec python3 -m uvicorn vayusutra_apix.api.main:app --host 0.0.0.0 --port 8000 --workers 4
