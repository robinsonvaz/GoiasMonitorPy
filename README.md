# GoiasMonitorPy

Sistema de monitoramento de notícias sobre órgãos, entidades, pessoas e empresas relacionadas ao estado de Goiás.

O projeto foi migrado para FastAPI e hoje inclui:
- coleta web e social com estratégia híbrida (Google News + web aberta)
- cobertura local embutida para portais goianos (RSS quando disponível, scraping quando necessário)
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

Para manter a aplicação rodando após fechar o terminal ou o VS Code:

```powershell
./start-app.ps1 -NoReload -Detached
```

Parar a instância desacoplada:

```powershell
./stop-app.ps1
```

Parâmetros úteis:

```powershell
./start-app.ps1 -Port 8001
./start-app.ps1 -HostAddr 0.0.0.0 -Port 8000
./start-app.ps1 -NoReload
./start-app.ps1 -NoReload -Detached
```

### Opção 2

```bat
run.bat
```

A aplicação sobe em `http://127.0.0.1:8000` por padrão.

## Execução em produção (Linux)

### Pré-requisitos

- Python 3.11
- MySQL 8.x ou MariaDB 10.6+
- Nginx
- (opcional) Certbot / Let's Encrypt

### 1. Criar usuário e diretório

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin goiasmonitor
sudo mkdir -p /opt/goiasmonitor
sudo chown goiasmonitor:goiasmonitor /opt/goiasmonitor
```

### 2. Clonar e configurar virtualenv

```bash
cd /opt/goiasmonitor
git clone <repo_url> .
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

```bash
cp .env.example .env
# Edite .env com suas credenciais de produção
nano .env
```

Gere uma chave secreta forte:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Cole o resultado em `APP_SECRET_KEY` no `.env`.

### 4. (Opcional) Instalar navegadores Playwright

```bash
.venv/bin/python -m playwright install chromium --with-deps
```

### 5. Registrar serviço systemd

```bash
sudo cp deploy/goiasmonitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable goiasmonitor
sudo systemctl start goiasmonitor
sudo systemctl status goiasmonitor
```

Verificar logs:

```bash
sudo journalctl -u goiasmonitor -f
```

### 6. Configurar Nginx como reverse proxy

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/goiasmonitor
# Edite o arquivo substituindo seudominio.com.br pelo domínio real
sudo nano /etc/nginx/sites-available/goiasmonitor

sudo ln -s /etc/nginx/sites-available/goiasmonitor \
           /etc/nginx/sites-enabled/goiasmonitor
sudo nginx -t && sudo systemctl reload nginx
```

### 7. Configurar TLS (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d seudominio.com.br -d www.seudominio.com.br
```

### Ajuste fino do Gunicorn

As configurações ficam em `gunicorn.conf.py`. Parâmetros overrideable por variáveis de ambiente:

| Variável | Padrão | Descrição |
|---|---|---|
| `GUNICORN_BIND` | `127.0.0.1:8000` | Endereço de escuta |
| `GUNICORN_WORKERS` | `1` | Processos workers (manter 1 por causa do APScheduler embutido) |
| `GUNICORN_TIMEOUT` | `120` | Timeout por requisição (segundos) |
| `GUNICORN_LOG_LEVEL` | `info` | Nível de log (`debug`, `info`, `warning`, `error`) |

> **Nota sobre workers:** O `APScheduler` roda dentro do processo da aplicação.
> Com múltiplos workers, cada processo teria um scheduler independente, causando
> execução duplicada dos agendamentos. Mantenha `GUNICORN_WORKERS=1` até migrar
> o scheduler para um mecanismo externo (Celery Beat, Redis, etc.).

### Estrutura dos artefatos de deploy

```text
deploy/
├── goiasmonitor.service  # unidade systemd
├── nginx.conf            # reverse proxy Nginx (referência)
└── start-prod.sh         # script de inicialização manual
gunicorn.conf.py          # configuração Gunicorn
.env.example              # template de variáveis de produção
```

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
1. Varredura obrigatória e prioritária de portais locais de Goiás (feeds nativos e páginas de listagem)
2. Complemento com Google Alerts (entidade + globais) e RSS configurados no `.env`
3. Busca em Google News (RSS e fallbacks) para expansão de cobertura
4. Expansão para web aberta quando necessário
5. Classificação de relevância/sentimento/classificação por IA
6. Enriquecimento de menções (pessoas/organizações/empresas)
7. Persistência em `news_items`
8. Geração de alertas para casos negativos


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

Além dos feeds configurados no `.env`, a aplicação agora também faz cobertura local embutida dos principais portais goianos. A estratégia usa RSS quando o portal expõe feed estável e cai para scraping de páginas de listagem quando isso não existe ou não é confiável.

Cobertura local embutida validada:
- Jornal Opção
- Diário de Goiás
- Diário do Estado
- Diário da Manhã
- O Hoje
- Portal 6
- Goiás 24 Horas
- Opinião Goiás
- A Redação
- Mais Goiás
- Dia Online
- Sagres Online
- Folha Z
- Oeste Goiano
- Tribuna do Planalto
- Zap Catalão
- Revista Bula
- Agência Goiás de Notícias (portal oficial)
- Jornal Visão
- O Popular, via scraping das páginas de editoria e últimas notícias

Se quiser, eu posso:
- ajudar a montar uma lista inicial de feeds goianos e verificar as URLs válidas
- ou adicionar exemplos reais ao `README.md` (posso buscar e validar os links)


## Reprocessamento de menções

Para recalcular o campo `people_mentioned` com as regras atuais em notícias já salvas:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts/reprocess_mentions.py
```

## Revalidacao de relevancia (falsos positivos)

Para revalidar noticias antigas com o filtro estrito (contexto de Goias + variacoes da entidade):

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts/revalidate_news_relevance.py --action report --print-false-positives
```

Executar em modo aplicacao (desassociar):

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts/revalidate_news_relevance.py --action detach --apply --fetch-missing-full-text
```

Executar em modo aplicacao (remover):

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts/revalidate_news_relevance.py --action delete --apply --fetch-missing-full-text
```

Revalidar apenas uma noticia especifica:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts/revalidate_news_relevance.py --news-id 76c987ac-f5e3-4ad5-837f-d682ef6ee439 --action report --print-false-positives
```

## Reclassificação de sentimento

Depois de ajustar os prompts em `prompts/news_classifier.txt` ou `prompts/social_classifier.txt`, execute o script abaixo para reclassificar **todas** as notícias já capturadas com o novo critério:

```powershell
.\.venv\Scripts\python.exe scripts/reclassify_fast.py
```

O script usa a cadeia de fallback de IA configurada no `.env` e exibe o progresso linha a linha. Ao final mostra a distribuição de sentimentos (positivo / negativo / neutro) resultante.

## Banco de dados

- O schema essencial é garantido automaticamente no startup via `ensure_local_schema()`.
- Tabelas-chave: `users`, `profiles`, `monitored_entities`, `news_items`, `alerts`.

## Observações de uso

- O dashboard exibe o total real de notícias da base e mantém uma lista recente separada para visualização rápida.
- Para produção, use segredo forte em `APP_SECRET_KEY` e credenciais de banco apropriadas.
