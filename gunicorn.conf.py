"""Gunicorn configuration — production.

Use: gunicorn -c gunicorn.conf.py app:app

O APScheduler roda dentro do processo da aplicação; por isso mantemos
worker_class = "uvicorn.workers.UvicornWorker" com workers = 1 para evitar
que múltiplos processos disparem os mesmos agendamentos simultaneamente.
Para escala horizontal, use um scheduler externo (Celery Beat, APScheduler
com store Redis, etc.) e eleve workers = 2..4.
"""
from __future__ import annotations

import multiprocessing
import os

# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------
# Mantido em 1 por causa do APScheduler in-process.
# Aumente apenas se migrar o scheduler para fora do processo.
workers = int(os.environ.get("GUNICORN_WORKERS", "1"))
worker_class = "uvicorn.workers.UvicornWorker"

# Threads por worker (útil para I/O-bound com worker_class síncrono;
# com UvicornWorker o event-loop já lida com concorrência).
threads = int(os.environ.get("GUNICORN_THREADS", "1"))

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")   # "-" → stdout
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")     # "-" → stderr
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# ---------------------------------------------------------------------------
# Process naming
# ---------------------------------------------------------------------------
proc_name = "goiasmonitor"

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
# Limita o tamanho da linha de requisição e dos headers.
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190
