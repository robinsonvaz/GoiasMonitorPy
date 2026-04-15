"""GoiasMonitorPy — Flask application entry point."""
from __future__ import annotations
import functools
from datetime import datetime
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    flash,
)
from config import FLASK_SECRET_KEY, FLASK_DEBUG
from supabase_client import get_anon_client

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("access_token"):
            return redirect(url_for("auth"))
        return view(*args, **kwargs)
    return wrapped


def current_user():
    return {
        "id": session.get("user_id"),
        "email": session.get("user_email"),
        "full_name": session.get("full_name", ""),
    }


def get_authed_client():
    """Return a Supabase client with the current user's JWT injected."""
    client = get_anon_client()
    token = session.get("access_token")
    if token:
        client.auth.set_session(token, session.get("refresh_token", ""))
    return client


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route("/auth", methods=["GET", "POST"])
def auth():
    if session.get("access_token"):
        return redirect(url_for("dashboard"))

    error = None
    if request.method == "POST":
        action = request.form.get("action", "login")
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()

        try:
            supa = get_anon_client()
            if action == "login":
                response = supa.auth.sign_in_with_password({"email": email, "password": password})
            else:
                response = supa.auth.sign_up({
                    "email": email,
                    "password": password,
                    "options": {"data": {"full_name": full_name}},
                })

            if response.session:
                session["access_token"] = response.session.access_token
                session["refresh_token"] = response.session.refresh_token
                session["user_id"] = response.user.id
                session["user_email"] = response.user.email
                session["full_name"] = (
                    response.user.user_metadata.get("full_name", "") if response.user.user_metadata else ""
                )
                return redirect(url_for("dashboard"))
            elif action == "register":
                flash("Conta criada! Verifique seu e-mail para confirmar o cadastro.", "success")
        except Exception as exc:
            error = str(exc)

    return render_template("auth.html", error=error)


@app.route("/logout")
def logout():
    try:
        supa = get_anon_client()
        supa.auth.sign_out()
    except Exception:
        pass
    session.clear()
    return redirect(url_for("auth"))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def dashboard():
    supa = get_authed_client()

    news_items = supa.table("news_items").select("*, monitored_entities(name)").order(
        "collected_at", desc=True
    ).limit(20).execute().data or []

    entities = supa.table("monitored_entities").select("*").eq("is_active", True).execute().data or []

    alerts = (
        supa.table("alerts").select("*").eq("is_read", False).order("created_at", desc=True).execute().data or []
    )

    negative_count = sum(1 for n in news_items if n.get("sentiment") == "negativo")

    class_breakdown: dict[str, int] = {}
    for n in news_items:
        c = n.get("classification", "outro")
        class_breakdown[c] = class_breakdown.get(c, 0) + 1

    return render_template(
        "dashboard.html",
        news_items=news_items,
        entities=entities,
        alerts=alerts,
        negative_count=negative_count,
        class_breakdown=class_breakdown,
        user=current_user(),
    )


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

@app.route("/noticias")
@login_required
def news():
    supa = get_authed_client()

    all_entities = supa.table("monitored_entities").select("id, name").order("name").execute().data or []
    news_items = (
        supa.table("news_items")
        .select("*, monitored_entities(name)")
        .order("collected_at", desc=True)
        .execute()
        .data or []
    )
    # Apply filters
    search = request.args.get("search", "").lower()
    class_filter = request.args.get("classification", "all")
    sentiment_filter = request.args.get("sentiment", "all")
    entity_filter = request.args.get("entity", "all")

    filtered = []
    for n in news_items:
        if search and search not in n.get("title", "").lower() and search not in (n.get("content") or "").lower():
            continue
        if class_filter != "all" and n.get("classification") != class_filter:
            continue
        if sentiment_filter != "all" and n.get("sentiment") != sentiment_filter:
            continue
        if entity_filter != "all" and n.get("entity_id") != entity_filter:
            continue
        filtered.append(n)

    return render_template(
        "news.html",
        news_items=filtered,
        entities=all_entities,
        filters={
            "search": search,
            "classification": class_filter,
            "sentiment": sentiment_filter,
            "entity": entity_filter,
        },
        user=current_user(),
    )


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

@app.route("/entidades", methods=["GET", "POST"])
@login_required
def entities():
    supa = get_authed_client()
    error = None

    if request.method == "POST":
        action = request.form.get("action", "create")
        entity_id = request.form.get("entity_id", "")
        name = request.form.get("name", "").strip()
        entity_type = request.form.get("entity_type", "orgao")
        description = request.form.get("description", "").strip() or None
        keywords_raw = request.form.get("keywords", "")
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]

        try:
            if action == "delete":
                supa.table("monitored_entities").delete().eq("id", entity_id).execute()
                flash("Entidade removida.", "success")
            elif action == "toggle":
                is_active = request.form.get("is_active") == "true"
                supa.table("monitored_entities").update({"is_active": is_active}).eq("id", entity_id).execute()
            elif action == "edit":
                supa.table("monitored_entities").update({
                    "name": name,
                    "entity_type": entity_type,
                    "description": description,
                    "keywords": keywords,
                    "created_by": current_user()["id"],
                }).eq("id", entity_id).execute()
                flash("Entidade atualizada.", "success")
            else:  # create
                supa.table("monitored_entities").insert({
                    "name": name,
                    "entity_type": entity_type,
                    "description": description,
                    "keywords": keywords,
                    "created_by": current_user()["id"],
                }).execute()
                flash("Entidade criada.", "success")
        except Exception as exc:
            error = str(exc)

        return redirect(url_for("entities"))

    all_entities = supa.table("monitored_entities").select("*").order("name").execute().data or []
    return render_template("entities.html", entities=all_entities, error=error, user=current_user())


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

@app.route("/alertas", methods=["GET", "POST"])
@login_required
def alerts():
    supa = get_authed_client()

    if request.method == "POST":
        action = request.form.get("action", "")
        alert_id = request.form.get("alert_id", "")
        try:
            if action == "mark_read":
                supa.table("alerts").update({"is_read": True}).eq("id", alert_id).execute()
            elif action == "mark_all_read":
                supa.table("alerts").update({"is_read": True}).eq("is_read", False).execute()
        except Exception:
            pass
        return redirect(url_for("alerts"))

    all_alerts = (
        supa.table("alerts")
        .select("*, news_items(title)")
        .order("created_at", desc=True)
        .execute()
        .data or []
    )
    unread_count = sum(1 for a in all_alerts if not a.get("is_read"))
    return render_template("alerts.html", alerts=all_alerts, unread_count=unread_count, user=current_user())


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

@app.route("/grafo")
@login_required
def graph():
    supa = get_authed_client()
    news_items = (
        supa.table("news_items")
        .select("*, monitored_entities(name)")
        .order("collected_at", desc=True)
        .execute()
        .data or []
    )
    return render_template("graph.html", news_items=news_items, user=current_user())


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.route("/configuracoes", methods=["GET", "POST"])
@login_required
def settings():
    supa = get_authed_client()
    user = current_user()
    error = None

    profile = None
    try:
        result = supa.table("profiles").select("*").eq("user_id", user["id"]).execute()
        if result.data:
            profile = result.data[0]
    except Exception:
        pass

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        try:
            if profile:
                supa.table("profiles").update({"full_name": full_name}).eq("user_id", user["id"]).execute()
            else:
                supa.table("profiles").insert({"full_name": full_name, "user_id": user["id"]}).execute()
            session["full_name"] = full_name
            flash("Perfil atualizado.", "success")
        except Exception as exc:
            error = str(exc)
        return redirect(url_for("settings"))

    entities = supa.table("monitored_entities").select("*").order("name").execute().data or []
    news_count_resp = supa.table("news_items").select("id", count="exact").execute()
    news_count = news_count_resp.count or 0

    return render_template(
        "settings.html",
        profile=profile,
        entities=entities,
        news_count=news_count,
        error=error,
        user=user,
    )


# ---------------------------------------------------------------------------
# API endpoints (AJAX)
# ---------------------------------------------------------------------------

@app.route("/api/collect-news", methods=["POST"])
@login_required
def api_collect_news():
    from agents import news_collector
    data = request.get_json(silent=True) or {}
    entity_id = data.get("entity_id")
    result = news_collector.run(entity_id=entity_id, user_id=current_user()["id"])
    return jsonify(result)


@app.route("/api/collect-news-social", methods=["POST"])
@login_required
def api_collect_news_social():
    from agents import social_collector
    data = request.get_json(silent=True) or {}
    entity_id = data.get("entity_id")
    result = social_collector.run(entity_id=entity_id, user_id=current_user()["id"])
    return jsonify(result)


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------

@app.template_filter("datetime_br")
def datetime_br(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return value or ""


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=FLASK_DEBUG, port=5000)
