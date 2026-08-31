"""
VayuSutra APIx - Vercel Serverless Function Entrypoint
Routes all incoming web, REST API, and WebSocket requests into the FastAPI Application.
"""

import sys
import os

# Set serverless environment flags
os.environ["VERCEL"] = "1"
os.environ["ENVIRONMENT"] = "production"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)

for path in [ROOT_DIR, CURRENT_DIR, os.getcwd()]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Import the primary FastAPI application
from vayusutra_apix.api.main import app

# Expose 'app' as the ASGI serverless handler for Vercel
app = app
