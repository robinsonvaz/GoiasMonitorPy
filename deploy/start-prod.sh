#!/usr/bin/env bash
# deploy/start-prod.sh — inicializa GoiasMonitorPy em produção (Linux)
#
# Uso direto (para testes manuais):
#   bash deploy/start-prod.sh
#
# Em produção, prefira o serviço systemd (deploy/goiasmonitor.service).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$APP_DIR/.venv"
PYTHON="$VENV_DIR/bin/python"
GUNICORN="$VENV_DIR/bin/gunicorn"

# ── Verificações básicas ───────────────────────────────────────────────────
if [[ ! -f "$APP_DIR/.env" ]]; then
    echo "ERRO: arquivo .env não encontrado em $APP_DIR" >&2
    echo "      Copie .env.example para .env e preencha as variáveis." >&2
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "ERRO: virtualenv não encontrado em $VENV_DIR" >&2
    echo "      Execute: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

if [[ ! -x "$GUNICORN" ]]; then
    echo "Gunicorn não encontrado — instalando dependências..." >&2
    "$PYTHON" -m pip install --quiet -r "$APP_DIR/requirements.txt"
fi

# ── Playwright: garante navegadores instalados ────────────────────────────
if grep -q "PLAYWRIGHT_ENABLED=true" "$APP_DIR/.env" 2>/dev/null; then
    "$PYTHON" -m playwright install chromium --with-deps 2>/dev/null || true
fi

# ── Diretório de trabalho ─────────────────────────────────────────────────
cd "$APP_DIR"

echo "Iniciando GoiasMonitorPy via Gunicorn..."
echo "  Config:  gunicorn.conf.py"
echo "  PID file: /tmp/goiasmonitor.pid"

exec "$GUNICORN" \
    -c "$APP_DIR/gunicorn.conf.py" \
    --pid /tmp/goiasmonitor.pid \
    app:app
