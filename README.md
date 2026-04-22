# GoiasMonitorPy

Versão Python/Flask do **GoiasMonitor** — sistema de monitoramento de notícias sobre órgãos e entidades do estado de Goiás.

## Tecnologias

- **Python 3.11** + **Flask**
- **MySQL local** (persistência 100% local)
- Agentes de coleta com **Firecrawl** / **ScrapingBee**
- Classificação por IA via **Lovable AI Gateway** (Gemini 2.5 Flash)
- Frontend em HTML/CSS com design dark idêntico ao original

## Estrutura

```
GoiasMonitorPy/
├── app.py                  # Aplicação Flask principal (todas as rotas)
├── config.py               # Variáveis de configuração
├── db.py                   # Conexão e helpers para banco MySQL local
├── agents/
│   ├── news_collector.py   # Agente de coleta de notícias na web
│   └── social_collector.py # Agente de coleta em redes sociais
├── tools/
│   ├── firecrawl.py        # Tool: busca via Firecrawl API
│   ├── scrapingbee.py      # Tool: busca via ScrapingBee API
│   └── ai_classifier.py    # Tool: classificação AI (Lovable Gateway)
├── prompts/
│   ├── news_classifier.txt # Prompt para classificação de notícias web
│   └── social_classifier.txt # Prompt para classificação de redes sociais
├── templates/              # Templates Jinja2 (HTML)
│   ├── base.html           # Layout base com sidebar
│   ├── auth.html           # Login/Cadastro
│   ├── dashboard.html      # Dashboard principal
│   ├── news.html           # Listagem de notícias com filtros
│   ├── entities.html       # CRUD de entidades monitoradas
│   ├── alerts.html         # Alertas (marcar como lido)
│   ├── graph.html          # Grafo D3.js de relacionamentos
│   └── settings.html       # Configurações e perfil
├── static/
│   ├── css/style.css       # Design system dark (replica Tailwind do original)
│   └── js/app.js           # JavaScript global (sidebar mobile, toasts)
└── .env                    # Variáveis de ambiente (não versionar)
```

## Configuração

### 1. Editar o `.env`

```env
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_DATABASE=goiasmonitor
LOCAL_ADMIN_EMAIL=admin@local
LOCAL_ADMIN_PASSWORD=admin123
LOCAL_ADMIN_NAME=Administrador Local
FLASK_SECRET_KEY=troque-esta-chave
LOVABLE_API_KEY=
FIRECRAWL_API_KEY=
SCRAPINGBEE_API_KEY=
```

### 2. Ativar o ambiente virtual

```powershell
.\.venv\Scripts\Activate.ps1
```

### 3. Executar

```powershell
python app.py
```

Acesse: **http://localhost:5000**

## Funcionalidades

| Página | Descrição |
|---|---|
| Dashboard | Estatísticas gerais, últimas notícias, breakdown por classificação |
| Notícias | Listagem com filtros por classificação, sentimento e entidade |
| Entidades | CRUD de entidades monitoradas (nome, tipo, keywords) |
| Alertas | Alertas gerados automaticamente na coleta, marcação como lido |
| Grafo | Visualização D3.js de relações notícias ↔ entidades ↔ pessoas |
| Configurações | Perfil do usuário e estatísticas do sistema |

## Coleta de Notícias

Os botões **"Coletar Web"** e **"Coletar Redes Sociais"** no Dashboard disparam as APIs:

- `POST /api/collect-news` → agente `news_collector.py`
- `POST /api/collect-news-social` → agente `social_collector.py`

Cada agente:
1. Busca na web via Firecrawl (com fallback para ScrapingBee)
2. Classifica cada resultado via AI (Gemini 2.5 Flash)
3. Insere os relevantes no banco local (MySQL)
4. Gera alertas automáticos para conteúdo negativo
