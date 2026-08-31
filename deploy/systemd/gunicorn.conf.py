# ==============================================================================
# VayuSutra APIx - Gunicorn Multi-Worker Production Server Configuration
# ==============================================================================

import multiprocessing
import os

bind = os.getenv("BIND", "0.0.0.0:8000")
workers = int(os.getenv("WORKERS_COUNT", multiprocessing.cpu_count() * 2 + 1))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
timeout = 120
keepalive = 65

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" (%(L)ss)'

# Process Naming & Lifecycle
proc_name = "vayusutra_apix_prod"
preload_app = False
daemon = False
max_requests = 2000
max_requests_jitter = 200
