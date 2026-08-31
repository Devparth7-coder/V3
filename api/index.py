"""
VayuSutra APIx - Vercel Serverless Function Entrypoint
Routes all incoming web, REST API, and WebSocket requests into the FastAPI Application.
"""

import sys
import os

# Add root directory to python path for Vercel Serverless runtime
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from vayusutra_apix.api.main import app

# Vercel Serverless Handler
app = app
