# GoiasMonitorPy

Sistema de monitoramento de notícias sobre órgãos, entidades, pessoas e empresas relacionadas ao estado de Goiás.

O projeto foi migrado para FastAPI e hoje inclui:
- coleta web e social com estratégia híbrida (Google News + web aberta)
- classificação por IA
- painel com métricas e filtros
- grafo de relacionamentos com destaque interativo por nível de conexão

## Stack

- Python 3.11
- FastAPI + Jinja2
- Pydantic Settings
- MySQL (persistência local)
- HTMX (ações assíncronas na UI)
- D3.js (grafo de relacionamentos)
- MyPy (tipagem estática)
- IA via Lovable AI Gateway (Gemini 2.5 Flash)

## Estrutura principal

```text
GoiasMonitorPy/
├── app.py
├── config.py
├── db.py
├── requirements.txt
├── requirements-dev.txt
├── mypy.ini
├── start-app.ps1
├── run.bat
├── agents/
│   ├── news_collector.py
│   └── social_collector.py
├── tools/
│   ├── ai_classifier.py
│   └── google_search.py
├── scripts/
│   └── reprocess_mentions.py
├── prompts/
│   ├── news_classifier.txt
│   └── social_classifier.txt
├── templates/
└── static/
```

## Configuração

Crie/edite o arquivo `.env` na raiz:

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_DATABASE=goiasmonitor

LOCAL_ADMIN_EMAIL=admin@local
LOCAL_ADMIN_PASSWORD=admin123
LOCAL_ADMIN_NAME=Administrador Local

APP_SECRET_KEY=troque-esta-chave
DEBUG=false

LOVABLE_API_KEY=

# Mantidas por compatibilidade
FIRECRAWL_API_KEY=
SCRAPINGBEE_API_KEY=
```

Observações:
- `APP_SECRET_KEY` é o nome preferencial (também aceita `FLASK_SECRET_KEY` por compatibilidade).
- `LOVABLE_API_KEY` é necessária para classificação e enriquecimento das notícias.

## Execução (Windows)

### Opção 1 (recomendada)

```powershell
./start-app.ps1
```

Parâmetros úteis:

```powershell
./start-app.ps1 -Port 8001
./start-app.ps1 -HostAddr 0.0.0.0 -Port 8000
./start-app.ps1 -NoReload
```

### Opção 2

```bat
run.bat
```

A aplicação sobe em `http://127.0.0.1:8000` por padrão.

## Instalação de dependências

Ambiente de runtime:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Ferramentas de desenvolvimento (inclui mypy):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Qualidade e tipagem

```powershell
.\.venv\Scripts\python.exe -m mypy .
```

Configuração em `mypy.ini` (modo estrito).

## Funcionalidades

- Dashboard com métricas gerais e últimas notícias
- Coleta web e social via botões da UI
- Notícias com filtros por texto, classificação, sentimento e entidade
- CRUD de entidades monitoradas
- Alertas com marcação de leitura
- Grafo com:
	- ícones distintos para pessoa, entidade e empresa
	- lista com filtro textual
	- seleção com destaque visual
	- expansão/recuo de vizinhança por passos (`+1` e `-1`)
- Configurações de perfil

## Estratégia de coleta

Endpoints:
- `POST /api/collect-news`
- `POST /api/collect-news-social`

Fluxo resumido:
1. Busca em Google News (RSS e fallbacks)
2. Expansão para web aberta quando necessário
3. Classificação de relevância/sentimento/classificação por IA
4. Enriquecimento de menções (pessoas/organizações/empresas)
5. Persistência em `news_items`
6. Geração de alertas para casos negativos

## Reprocessamento de menções

Para recalcular o campo `people_mentioned` com as regras atuais em notícias já salvas:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts/reprocess_mentions.py
```

## Banco de dados

- O schema essencial é garantido automaticamente no startup via `ensure_local_schema()`.
- Tabelas-chave: `users`, `profiles`, `monitored_entities`, `news_items`, `alerts`.

## Observações de uso

- O dashboard exibe o total real de notícias da base e mantém uma lista recente separada para visualização rápida.
- Para produção, use segredo forte em `APP_SECRET_KEY` e credenciais de banco apropriadas.
