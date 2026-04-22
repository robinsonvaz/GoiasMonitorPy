"""GoiasMonitorPy — FastAPI application entry point."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Annotated, Any, Callable

from fastapi import Depends, FastAPI, Form, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from werkzeug.security import check_password_hash, generate_password_hash

from config import settings
from db import ensure_local_schema, parse_json_list, query_all, query_one, execute

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="GoiasMonitorPy")
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    max_age=86400 * 30,
)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def _make_url_for(fastapi_app: FastAPI) -> Callable[..., str]:
    """Flask-compatible url_for() global for Jinja2 templates."""
    def url_for(name: str, **values: Any) -> str:
        if name == "static":
            filename: str = values.pop("filename", values.pop("path", ""))
            return str(fastapi_app.url_path_for("static", path=filename))
        return str(fastapi_app.url_path_for(name, **values))
    return url_for


templates.env.globals["url_for"] = _make_url_for(app)


def _datetime_br(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(value)


templates.env.filters["datetime_br"] = _datetime_br

ensure_local_schema()

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


class _RequiresLogin(Exception):
    pass


@app.exception_handler(_RequiresLogin)
async def _requires_login_handler(request: Request, exc: _RequiresLogin) -> RedirectResponse:
    return RedirectResponse(url="/auth", status_code=302)


def _flash(request: Request, message: str, category: str = "info") -> None:
    flashes: list[dict[str, str]] = request.session.get("_flashes", [])
    flashes.append({"category": category, "message": message})
    request.session["_flashes"] = flashes


def _render(request: Request, template: str, **ctx: Any) -> HTMLResponse:
    flashes: list[dict[str, str]] = request.session.pop("_flashes", [])
    endpoint_fn = request.scope.get("endpoint")
    current_page: str = getattr(endpoint_fn, "__name__", "")
    return templates.TemplateResponse(
        request=request,
        name=template,
        context={"flashed_messages": flashes, "current_page": current_page, **ctx},
    )


async def _require_login(request: Request) -> dict[str, str]:
    if not request.session.get("user_id"):
        raise _RequiresLogin()
    return {
        "id": request.session["user_id"],
        "email": request.session.get("user_email", ""),
        "full_name": request.session.get("full_name", ""),
    }


UserDep = Annotated[dict[str, str], Depends(_require_login)]

# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------


@app.get("/auth", response_class=HTMLResponse, name="auth")
async def auth(request: Request) -> Response:
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=302)
    return _render(request, "auth.html", error=None)


@app.post("/auth", response_class=HTMLResponse)
async def auth_post(
    request: Request,
    action: Annotated[str, Form()] = "login",
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    full_name: Annotated[str, Form()] = "",
) -> Response:
    email = email.strip().lower()
    full_name = full_name.strip()
    error: str | None = None
    try:
        if action == "login":
            user = query_one("SELECT * FROM users WHERE email = %s", (email,))
            if not user or not check_password_hash(user["password_hash"], password):
                raise ValueError("E-mail ou senha inválidos")
            request.session["user_id"] = user["id"]
            request.session["user_email"] = user["email"]
            request.session["full_name"] = user.get("full_name") or ""
            return RedirectResponse(url="/", status_code=303)
        # register
        if not email or not password:
            raise ValueError("Preencha e-mail e senha")
        if query_one("SELECT id FROM users WHERE email = %s", (email,)):
            raise ValueError("Já existe uma conta com este e-mail")
        user_id = str(uuid.uuid4())
        name = full_name or email.split("@")[0]
        execute(
            "INSERT INTO users (id, email, full_name, password_hash) VALUES (%s, %s, %s, %s)",
            (user_id, email, name, generate_password_hash(password)),
        )
        execute(
            "INSERT INTO profiles (id, user_id, full_name, avatar_url, created_at, updated_at)"
            " VALUES (%s, %s, %s, NULL, NOW(6), NOW(6))",
            (str(uuid.uuid4()), user_id, name),
        )
        request.session["user_id"] = user_id
        request.session["user_email"] = email
        request.session["full_name"] = name
        _flash(request, "Conta criada com sucesso.", "success")
        return RedirectResponse(url="/", status_code=303)
    except Exception as exc:
        error = str(exc)
    return _render(request, "auth.html", error=error)


@app.get("/logout", name="logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/auth", status_code=302)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse, name="dashboard")
async def dashboard(request: Request, user: UserDep) -> HTMLResponse:
    recent_news_items: list[dict[str, Any]] = query_all(
        """
        SELECT n.*, e.name AS entity_name
        FROM news_items n
        LEFT JOIN monitored_entities e ON e.id = n.entity_id
        ORDER BY n.collected_at DESC
        LIMIT 20
        """
    )
    for n in recent_news_items:
        n["people_mentioned"] = parse_json_list(n.get("people_mentioned"))
        n["monitored_entities"] = {"name": n.pop("entity_name")} if n.get("entity_name") else None

    total_news_row = query_one("SELECT COUNT(*) AS total FROM news_items")
    total_news_count = int(total_news_row["total"]) if total_news_row else 0

    negative_row = query_one(
        "SELECT COUNT(*) AS total FROM news_items WHERE sentiment = 'negativo'"
    )
    negative_count = int(negative_row["total"]) if negative_row else 0

    class_rows: list[dict[str, Any]] = query_all(
        "SELECT classification, COUNT(*) AS total FROM news_items GROUP BY classification"
    )
    class_breakdown: dict[str, int] = {
        str(row.get("classification") or "outro"): int(row.get("total") or 0)
        for row in class_rows
    }

    entities: list[dict[str, Any]] = query_all(
        "SELECT * FROM monitored_entities WHERE is_active = 1 ORDER BY name"
    )
    alerts: list[dict[str, Any]] = query_all(
        "SELECT * FROM alerts WHERE user_id = %s AND is_read = 0 ORDER BY created_at DESC",
        (user["id"],),
    )

    return _render(
        request,
        "dashboard.html",
        news_items=recent_news_items,
        total_news_count=total_news_count,
        entities=entities,
        alerts=alerts,
        negative_count=negative_count,
        class_breakdown=class_breakdown,
        user=user,
    )


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------


@app.get("/noticias", response_class=HTMLResponse, name="news")
async def news(
    request: Request,
    user: UserDep,
    search: str = "",
    classification: str = "all",
    sentiment: str = "all",
    entity: str = "all",
) -> HTMLResponse:
    all_entities: list[dict[str, Any]] = query_all(
        "SELECT id, name FROM monitored_entities ORDER BY name"
    )
    news_items: list[dict[str, Any]] = query_all(
        """
        SELECT n.*, e.name AS entity_name
        FROM news_items n
        LEFT JOIN monitored_entities e ON e.id = n.entity_id
        ORDER BY n.collected_at DESC
        """
    )
    for n in news_items:
        n["people_mentioned"] = parse_json_list(n.get("people_mentioned"))
        n["monitored_entities"] = {"name": n.pop("entity_name")} if n.get("entity_name") else None

    search_lower = search.lower()
    filtered = [
        n for n in news_items
        if (not search_lower
            or search_lower in (n.get("title") or "").lower()
            or search_lower in (n.get("content") or "").lower())
        and (classification == "all" or n.get("classification") == classification)
        and (sentiment == "all" or n.get("sentiment") == sentiment)
        and (entity == "all" or n.get("entity_id") == entity)
    ]
    return _render(
        request,
        "news.html",
        news_items=filtered,
        entities=all_entities,
        filters={
            "search": search,
            "classification": classification,
            "sentiment": sentiment,
            "entity": entity,
        },
        user=user,
    )


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@app.get("/entidades", response_class=HTMLResponse, name="entities")
async def entities(request: Request, user: UserDep) -> HTMLResponse:
    all_entities: list[dict[str, Any]] = query_all(
        "SELECT * FROM monitored_entities ORDER BY name"
    )
    for e in all_entities:
        e["keywords"] = parse_json_list(e.get("keywords"))
    return _render(request, "entities.html", entities=all_entities, error=None, user=user)


@app.post("/entidades", response_class=HTMLResponse)
async def entities_post(
    request: Request,
    user: UserDep,
    action: Annotated[str, Form()] = "create",
    entity_id: Annotated[str, Form()] = "",
    name: Annotated[str, Form()] = "",
    entity_type: Annotated[str, Form()] = "orgao",
    description: Annotated[str, Form()] = "",
    keywords: Annotated[str, Form()] = "",
    is_active: Annotated[str, Form()] = "",
) -> Response:
    keywords_list = [k.strip() for k in keywords.split(",") if k.strip()]
    description_val: str | None = description.strip() or None
    error: str | None = None
    try:
        if action == "delete":
            execute(
                "DELETE FROM monitored_entities WHERE id = %s AND created_by = %s",
                (entity_id, user["id"]),
            )
            _flash(request, "Entidade removida.", "success")
        elif action == "toggle":
            execute(
                "UPDATE monitored_entities SET is_active = %s WHERE id = %s",
                (1 if is_active == "true" else 0, entity_id),
            )
        elif action == "edit":
            execute(
                "UPDATE monitored_entities SET name=%s, entity_type=%s, description=%s,"
                " keywords=%s, updated_at=NOW(6) WHERE id=%s",
                (
                    name.strip(), entity_type, description_val,
                    json.dumps(keywords_list, ensure_ascii=False), entity_id,
                ),
            )
            _flash(request, "Entidade atualizada.", "success")
        else:
            execute(
                "INSERT INTO monitored_entities"
                " (id, name, entity_type, description, keywords, is_active, created_by,"
                "  created_at, updated_at)"
                " VALUES (%s, %s, %s, %s, %s, 1, %s, NOW(6), NOW(6))",
                (
                    str(uuid.uuid4()), name.strip(), entity_type, description_val,
                    json.dumps(keywords_list, ensure_ascii=False), user["id"],
                ),
            )
            _flash(request, "Entidade criada.", "success")
    except Exception as exc:
        error = str(exc)

    if error:
        all_entities: list[dict[str, Any]] = query_all(
            "SELECT * FROM monitored_entities ORDER BY name"
        )
        for e in all_entities:
            e["keywords"] = parse_json_list(e.get("keywords"))
        return _render(request, "entities.html", entities=all_entities, error=error, user=user)

    return RedirectResponse(url="/entidades", status_code=303)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@app.get("/alertas", response_class=HTMLResponse, name="alerts")
async def alerts(request: Request, user: UserDep) -> HTMLResponse:
    all_alerts: list[dict[str, Any]] = query_all(
        """
        SELECT a.*, n.title AS news_title
        FROM alerts a
        LEFT JOIN news_items n ON n.id = a.news_item_id
        WHERE a.user_id = %s
        ORDER BY a.created_at DESC
        """,
        (user["id"],),
    )
    for a in all_alerts:
        a["news_items"] = {"title": a.pop("news_title")} if a.get("news_title") else None

    unread_count = sum(1 for a in all_alerts if not a.get("is_read"))
    return _render(request, "alerts.html", alerts=all_alerts, unread_count=unread_count, user=user)


@app.post("/alertas", response_class=HTMLResponse)
async def alerts_post(
    request: Request,
    user: UserDep,
    action: Annotated[str, Form()] = "",
    alert_id: Annotated[str, Form()] = "",
) -> RedirectResponse:
    try:
        if action == "mark_read":
            execute(
                "UPDATE alerts SET is_read = 1 WHERE id = %s AND user_id = %s",
                (alert_id, user["id"]),
            )
        elif action == "mark_all_read":
            execute(
                "UPDATE alerts SET is_read = 1 WHERE user_id = %s AND is_read = 0",
                (user["id"],),
            )
    except Exception:
        pass
    return RedirectResponse(url="/alertas", status_code=303)


@app.post("/api/alertas/{alert_id}/read", name="api_mark_alert_read")
async def api_mark_alert_read(
    request: Request,
    alert_id: str,
    user: UserDep,
) -> HTMLResponse:
    """HTMX endpoint — mark an alert as read and return the updated card fragment."""
    execute(
        "UPDATE alerts SET is_read = 1 WHERE id = %s AND user_id = %s",
        (alert_id, user["id"]),
    )
    alert: dict[str, Any] | None = query_one(
        "SELECT a.*, n.title AS news_title"
        " FROM alerts a"
        " LEFT JOIN news_items n ON n.id = a.news_item_id"
        " WHERE a.id = %s",
        (alert_id,),
    )
    if alert:
        alert["news_items"] = {"title": alert.pop("news_title")} if alert.get("news_title") else None
    return templates.TemplateResponse(
        request=request,
        name="partials/alert_card.html",
        context={"alert": alert},
    )


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


@app.get("/grafo", response_class=HTMLResponse, name="graph")
async def graph(request: Request, user: UserDep) -> HTMLResponse:
    news_items: list[dict[str, Any]] = query_all(
        """
        SELECT n.*, e.name AS entity_name
        FROM news_items n
        LEFT JOIN monitored_entities e ON e.id = n.entity_id
        ORDER BY n.collected_at DESC
        """
    )
    for n in news_items:
        n["people_mentioned"] = parse_json_list(n.get("people_mentioned"))
        n["monitored_entities"] = {"name": n.pop("entity_name")} if n.get("entity_name") else None
    news_items_json = jsonable_encoder(news_items)
    return _render(request, "graph.html", news_items_json=news_items_json, user=user)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@app.get("/configuracoes", response_class=HTMLResponse, name="settings")
async def settings_get(request: Request, user: UserDep) -> HTMLResponse:
    profile: dict[str, Any] | None = query_one(
        "SELECT * FROM profiles WHERE user_id = %s", (user["id"],)
    )
    entities: list[dict[str, Any]] = query_all(
        "SELECT * FROM monitored_entities ORDER BY name"
    )
    row = query_one("SELECT COUNT(*) AS total FROM news_items")
    news_count: int = row["total"] if row else 0
    return _render(
        request, "settings.html",
        profile=profile, entities=entities, news_count=news_count, error=None, user=user,
    )


@app.post("/configuracoes", response_class=HTMLResponse)
async def settings_post(
    request: Request,
    user: UserDep,
    full_name: Annotated[str, Form()] = "",
) -> Response:
    full_name = full_name.strip()
    is_htmx = request.headers.get("HX-Request") == "true"
    error: str | None = None
    try:
        profile = query_one("SELECT * FROM profiles WHERE user_id = %s", (user["id"],))
        if profile:
            execute(
                "UPDATE profiles SET full_name = %s, updated_at = NOW(6) WHERE user_id = %s",
                (full_name, user["id"]),
            )
        else:
            execute(
                "INSERT INTO profiles (id, user_id, full_name, avatar_url, created_at, updated_at)"
                " VALUES (%s, %s, %s, NULL, NOW(6), NOW(6))",
                (str(uuid.uuid4()), user["id"], full_name),
            )
        execute("UPDATE users SET full_name = %s WHERE id = %s", (full_name, user["id"]))
        request.session["full_name"] = full_name
        if is_htmx:
            resp = Response(status_code=204)
            resp.headers["HX-Trigger"] = json.dumps(
                {"showToast": {"message": "Perfil atualizado.", "type": "success"}}
            )
            return resp
        _flash(request, "Perfil atualizado.", "success")
        return RedirectResponse(url="/configuracoes", status_code=303)
    except Exception as exc:
        error = str(exc)

    entities: list[dict[str, Any]] = query_all("SELECT * FROM monitored_entities ORDER BY name")
    row = query_one("SELECT COUNT(*) AS total FROM news_items")
    news_count = row["total"] if row else 0
    profile = query_one("SELECT * FROM profiles WHERE user_id = %s", (user["id"],))
    return _render(
        request, "settings.html",
        profile=profile, entities=entities, news_count=news_count, error=error, user=user,
    )


# ---------------------------------------------------------------------------
# API endpoints (HTMX / AJAX)
# ---------------------------------------------------------------------------


@app.post("/api/collect-news", name="api_collect_news")
async def api_collect_news(request: Request, user: UserDep) -> JSONResponse:
    from agents import news_collector  # noqa: PLC0415

    entity_id: str | None = None
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body: dict[str, Any] = await request.json()
        entity_id = body.get("entity_id")

    result: dict[str, Any] = news_collector.run(entity_id=entity_id, user_id=user["id"])
    headers: dict[str, str] = {}
    if result.get("success"):
        msg = f"Coleta web: {result.get('collected', 0)} notícia(s)."
        if result.get("message"):
            msg += f" {result['message']}"
        headers["HX-Trigger"] = json.dumps(
            {"showToast": {"message": msg, "type": "success", "reload": True}}
        )
    else:
        headers["HX-Trigger"] = json.dumps(
            {"showToast": {"message": result.get("error", "Erro na coleta"), "type": "error"}}
        )
    return JSONResponse(result, headers=headers)


@app.post("/api/collect-news-social", name="api_collect_news_social")
async def api_collect_news_social(request: Request, user: UserDep) -> JSONResponse:
    from agents import social_collector  # noqa: PLC0415

    entity_id = None
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        entity_id = body.get("entity_id")

    result: dict[str, Any] = social_collector.run(entity_id=entity_id, user_id=user["id"])
    headers: dict[str, str] = {}
    if result.get("success"):
        msg = f"Coleta social: {result.get('collected', 0)} post(s)."
        if result.get("message"):
            msg += f" {result['message']}"
        headers["HX-Trigger"] = json.dumps(
            {"showToast": {"message": msg, "type": "success", "reload": True}}
        )
    else:
        headers["HX-Trigger"] = json.dumps(
            {"showToast": {"message": result.get("error", "Erro na coleta"), "type": "error"}}
        )
    return JSONResponse(result, headers=headers)


