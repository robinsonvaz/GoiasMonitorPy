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


## Google Alerts e Feeds RSS

Recomendamos complementar a coleta com assinaturas de feeds RSS e com Google Alerts entregues via RSS. Essas fontes gratuitas ajudam a garantir cobertura sem depender exclusivamente de APIs pagas.

Como criar um Google Alert com entrega via RSS:

1. Acesse https://google.com/alerts e faça login com sua conta Google pessoal.
2. Na caixa de busca, digite sua consulta (ex.: "Governo de Goiás" OR "Goiás" OR "Alego" + nome da entidade).
3. Clique em "Mostrar opções" (ou no ícone de lápis) e, em "Enviar para"/"Deliver to", escolha a opção de "Feed RSS" quando disponível.
4. Depois de salvar, clique no ícone de feed (pequeno quadrado laranja) ao lado do alerta para obter a URL do RSS.
5. Copie essa URL e adicione-a à configuração `GOOGLE_ALERTS_RSS` ou `google_alerts_rss` no seu `.env` (veja exemplo abaixo).

Como encontrar feeds RSS de sites locais (exemplos goianos):

- G1 Goiás — procurar o ícone de RSS na página regional do G1 (ex.: página "Goiás" do G1).
- Jornais locais (ex.: O Popular, Diário da Manhã) — as seções de notícias costumam expor um feed ou `/{feed,rss}`.
- Portal do Governo de Goiás — seção de notícias/assessoria de imprensa do governo estadual.
- Assembleia Legislativa de Goiás (ALEGO) — seção de notícias da ALEGO.
- Tribunal de Justiça de Goiás (TJ-GO) — seção de notícias do tribunal.

Observação: cada site publica o feed em caminhos diferentes (por exemplo `/feed`, `/rss`, ou `/rss.xml`). Procure o ícone de RSS ou use a busca no site por "RSS".

Exemplo de variáveis no `.env` (JSON arrays aceitos pelo `pydantic`):

```env
RSS_FEEDS=[
	"https://g1.globo.com/goias/",            # verificar o caminho /rss no site
	"https://opopular.com.br/feed/"           # exemplo: jornal local
]

GOOGLE_ALERTS_RSS=[
	"https://alerts.google.com/u/0/feeds/1234567890123456789"  # copie a URL do seu alerta
]
```

Após adicionar as URLs, rode a coleta normalmente; o agente já tentará consumir `RSS_FEEDS` e `GOOGLE_ALERTS_RSS` antes de recorrer às buscas.

Se quiser, eu posso:
- ajudar a montar uma lista inicial de feeds goianos e verificar as URLs válidas
- ou adicionar exemplos reais ao `README.md` (posso buscar e validar os links)


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
