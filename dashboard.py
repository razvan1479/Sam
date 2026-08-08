# dashboard.py — dashboard web (Flask) pentru marketplace.
# Rulează în același proces cu botul, într-un thread separat, pe alt port (implicit 5001).
# Protejat cu parolă: setează DASHBOARD_PASSWORD în .env.

import os
import hmac
import secrets as pysecrets
import asyncio
import datetime

from flask import Flask, render_template, request, redirect, url_for, session

import db
import store
import config

app = Flask(__name__)
app.secret_key = os.getenv("DASHBOARD_SECRET") or pysecrets.token_hex(32)

# Referință către bot (setată din bot.py) — necesară pentru acțiuni care ating Discord-ul.
bot = None


# =========================================================
#  Login — totul e protejat de parolă (DASHBOARD_PASSWORD din .env)
# =========================================================

def _password() -> str:
    return os.getenv("DASHBOARD_PASSWORD", "")


@app.before_request
def _require_login():
    if request.endpoint in ("login", "static"):
        return None
    if session.get("auth"):
        return None
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    pw = _password()
    error = None
    if request.method == "POST":
        if not pw:
            error = "Parola nu e setată pe server (DASHBOARD_PASSWORD în .env)."
        elif hmac.compare_digest(request.form.get("password", ""), pw):
            session["auth"] = True
            return redirect(url_for("overview"))
        else:
            error = "Parolă greșită."
    return render_template("login.html", error=error, pw_missing=(not pw))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def set_bot(b):
    global bot
    bot = b


@app.template_filter("dt")
def _format_ts(ts):
    if not ts:
        return "—"
    return datetime.datetime.fromtimestamp(int(ts)).strftime("%d.%m.%Y %H:%M")


# ============ Pagini ============

@app.route("/")
def overview():
    return render_template("overview.html", stats=db.get_overview_stats(), active="overview")


@app.route("/announcements")
def announcements():
    return render_template("announcements.html", rows=db.list_announcements(), active="announcements")


@app.route("/tickets")
def tickets():
    gid = store.first_guild_id()
    s = store.get_guild(gid) if gid else {}
    categories = []
    if bot is not None and gid:
        g = bot.get_guild(gid)
        if g:
            categories = [(c.id, c.name) for c in g.categories]
    return render_template("tickets.html", rows=db.list_tickets(), active="tickets",
                           categories=categories, ticket_category_id=s.get("ticket_category_id"))


@app.route("/tickets/settings", methods=["POST"])
def tickets_settings():
    gid = store.first_guild_id()
    if gid:
        cat = request.form.get("category_id", "").strip()
        store.set_guild_value(gid, "ticket_category_id", int(cat) if cat.isdigit() else None)
    return redirect(url_for("tickets"))


@app.route("/blacklist")
def blacklist():
    return render_template("blacklist.html", rows=db.list_blacklist(), active="blacklist")


@app.route("/logs")
def logs():
    return render_template("logs.html", rows=db.list_logs(), active="logs")


# Lista comenzilor botului (referință, ca să nu le ții minte)
COMMANDS = [
    ("Marketplace (admin)", [
        ("/marketplace setup", "canal [rol_intermediar] [categorie] [canal_loguri]",
         "Setează canalul marketplace și postează panoul; opțional rolul de intermediar, categoria ticketelor și canalul de loguri."),
        ("/marketplace panel", "", "Regenerează mesajul permanent al panoului."),
        ("/marketplace delete", "anunt:<id>", "Șterge un anunț și închide ticketele lui."),
        ("/marketplace stats", "[utilizator]", "Statistici globale sau ale unui utilizator."),
        ("/marketplace logs", "[canal]", "Setează sau arată canalul de loguri."),
        ("/marketplace blacklist", "utilizator [motiv]", "Restricționează un utilizator de la marketplace."),
        ("/marketplace unblock", "utilizator", "Îl scoate de pe blacklist."),
        ("/marketplace reload", "", "Reîncarcă modulul fără restart."),
    ]),
    ("Calendar (admin)", [
        ("/adauga", "data:YYYY-MM-DD descriere [ora:HH:MM]", "Adaugă un eveniment în calendar."),
        ("/sterge", "id:<număr>", "Șterge un eveniment după ID."),
        ("/lista", "", "Arată evenimentele programate."),
        ("/seteaza_canal", "canal", "Setează canalul calendarului."),
        ("/seteaza_ora_notificare", "ora:HH:MM", "Setează ora notificării zilnice."),
        ("/regenereaza", "", "Recreează mesajul cu calendarul."),
    ]),
    ("Leaderboard promoteri (admin)", [
        ("/promoter setup", "canal rol [categorie]", "Configurează clasamentul (canal, rolul Promoter, categoria canalelor)."),
        ("/promoter add", "membru", "Adaugă un promoter: creează canal privat, dă rolul și îl bagă în clasament."),
        ("/promoter remove", "membru", "Scoate un promoter: șterge canalul și rolul."),
        ("/promoter regenereaza", "", "Repostează clasamentul."),
    ]),
    ("Bun venit / Rămas bun", [
        ("(fără comenzi)", "", "Se configurează din paginile Bun venit și Rămas bun ale dashboard-ului."),
    ]),
]


@app.route("/commands")
def commands():
    return render_template("commands.html", groups=COMMANDS, active="commands")


# ============ Calendar ============

def _refresh_calendar(gid):
    """Cere botului să reîmprospăteze mesajul fixat cu calendarul."""
    if bot is None or bot.loop is None:
        return
    guild = bot.get_guild(gid)
    cog = bot.get_cog("Calendar")
    if guild and cog:
        asyncio.run_coroutine_threadsafe(cog.refresh_calendar(guild), bot.loop)


def _valid_hhmm(v):
    try:
        datetime.datetime.strptime(v, "%H:%M")
        return True
    except ValueError:
        return False


@app.route("/calendar")
def calendar():
    gid = store.first_guild_id()
    s = store.get_guild(gid) if gid else {}
    events = db.list_events(gid) if gid else []
    channels = []
    if bot is not None and gid:
        g = bot.get_guild(gid)
        if g:
            channels = [(c.id, c.name) for c in g.text_channels]
    return render_template(
        "calendar.html", active="calendar", events=events, channels=channels,
        channel_id=s.get("calendar_channel_id"), notify_hour=s.get("notify_hour", "08:00"),
        today_label=s.get("cal_today_label") or config.CAL_TODAY_LABEL,
        upcoming_label=s.get("cal_upcoming_label") or config.CAL_UPCOMING_LABEL,
        empty_label=s.get("cal_empty_label") or config.CAL_EMPTY_LABEL,
        notify_header=s.get("cal_notify_header") or config.CAL_NOTIFY_HEADER,
    )


@app.route("/calendar/settings", methods=["POST"])
def calendar_settings():
    gid = store.first_guild_id()
    if not gid:
        return redirect(url_for("calendar"))
    ch = request.form.get("channel_id", "").strip()
    hour = request.form.get("notify_hour", "").strip()
    if ch.isdigit():
        store.set_guild_value(gid, "calendar_channel_id", int(ch))
        store.set_guild_value(gid, "calendar_message_id", None)
        store.set_guild_value(gid, "last_calendar_hour", None)
        _refresh_calendar(gid)
    if hour and _valid_hhmm(hour):
        store.set_guild_value(gid, "notify_hour", hour)
    # texte configurabile
    for key, field in [("cal_today_label", "today_label"),
                       ("cal_upcoming_label", "upcoming_label"),
                       ("cal_empty_label", "empty_label"),
                       ("cal_notify_header", "notify_header")]:
        store.set_guild_value(gid, key, request.form.get(field, "").strip() or None)
    _refresh_calendar(gid)
    return redirect(url_for("calendar"))


@app.route("/calendar/event/add", methods=["POST"])
def calendar_event_add():
    gid = store.first_guild_id()
    date = request.form.get("date", "").strip()
    time_ = request.form.get("time", "").strip() or None
    desc = request.form.get("description", "").strip()
    ok_date = True
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        ok_date = False
    if gid and ok_date and desc and (time_ is None or _valid_hhmm(time_)):
        db.add_event(gid, date, time_, desc)
        db.add_log(gid, "📅 Eveniment adăugat (dashboard)",
                   f"{date}" + (f" {time_}" if time_ else "") + f" · {desc}")
        _refresh_calendar(gid)
    return redirect(url_for("calendar"))


@app.route("/calendar/event/delete", methods=["POST"])
def calendar_event_delete():
    gid = store.first_guild_id()
    eid = int(request.form["event_id"])
    if gid:
        db.delete_event(eid, gid)
        db.add_log(gid, "📅 Eveniment șters (dashboard)", f"ID: {eid}")
        _refresh_calendar(gid)
    return redirect(url_for("calendar"))


# ============ Bun venit / Rămas bun ============

def _channels_for(gid):
    if bot is not None and gid:
        g = bot.get_guild(gid)
        if g:
            return [(c.id, c.name) for c in g.text_channels]
    return []


def _greeting_page(kind, label):
    gid = store.first_guild_id()
    cfg = (store.get_guild(gid) if gid else {}).get(kind, {})
    return render_template("greeting.html", active=kind, kind=kind, label=label,
                           cfg=cfg, channels=_channels_for(gid))


@app.route("/welcome")
def welcome_page():
    return _greeting_page("welcome", "Bun venit")


@app.route("/goodbye")
def goodbye_page():
    return _greeting_page("goodbye", "Rămas bun")


@app.route("/greeting/save", methods=["POST"])
def greeting_save():
    gid = store.first_guild_id()
    kind = request.form.get("kind")
    if gid and kind in ("welcome", "goodbye"):
        ch = request.form.get("channel_id", "")
        store.set_guild_value(gid, kind, {
            "enabled": request.form.get("enabled") == "on",
            "channel_id": int(ch) if ch.isdigit() else None,
            "title": request.form.get("title", "").strip(),
            "message": request.form.get("message", "").strip(),
            "use_embed": request.form.get("use_embed") == "on",
            "show_avatar": request.form.get("show_avatar") == "on",
            "color": request.form.get("color", "#5865f2").strip(),
        })
        return redirect(url_for(kind + "_page"))
    return redirect(url_for("overview"))


@app.route("/reset/market", methods=["POST"])
def reset_market():
    gid = store.first_guild_id()
    if gid:
        db.reset_marketplace(gid)
    return redirect(url_for("overview"))


@app.route("/reset/players", methods=["POST"])
def reset_players():
    gid = store.first_guild_id()
    if gid:
        db.reset_players(gid)
    return redirect(url_for("overview"))


@app.route("/reset/player", methods=["POST"])
def reset_player_route():
    gid = store.first_guild_id()
    uid = request.form.get("user_id", "").strip()
    if gid and uid.isdigit():
        db.reset_player(gid, int(uid))
    return redirect(url_for("overview"))


@app.route("/reset/tickets", methods=["POST"])
def reset_tickets_route():
    gid = store.first_guild_id()
    if gid:
        db.reset_tickets(gid)
    return redirect(url_for("overview"))


# ============ Acțiuni ============

@app.route("/blacklist/add", methods=["POST"])
def blacklist_add():
    uid = request.form.get("user_id", "").strip()
    reason = request.form.get("reason", "").strip() or None
    gid = store.first_guild_id()
    if uid.isdigit() and gid:
        db.add_global_block(gid, int(uid), reason)
        db.add_log(gid, "⛔ Blacklist (dashboard)",
                   f"User: {uid}" + (f" · Motiv: {reason}" if reason else ""))
    return redirect(url_for("blacklist"))


@app.route("/blacklist/remove", methods=["POST"])
def blacklist_remove():
    gid = int(request.form["guild_id"])
    uid = int(request.form["user_id"])
    db.remove_global_block(gid, uid)
    db.add_log(gid, "✅ Scos de pe blacklist (dashboard)", f"User: {uid}")
    return redirect(url_for("blacklist"))


async def _delete_announcement_coro(ann_id):
    """Rulează pe loop-ul botului: închide ticketele + șterge mesajul anunțului de pe Discord."""
    ann = db.get_announcement(ann_id)
    if not ann:
        return
    for t in db.get_active_tickets_for_announcement(ann_id):
        db.set_ticket_status(t["id"], "closed")
        guild = bot.get_guild(t["guild_id"])
        ch = guild.get_channel(t["channel_id"]) if guild and t.get("channel_id") else None
        if ch is not None:
            try:
                await ch.send("Anunțul a fost șters de administrație. Ticketul se închide.")
                await asyncio.sleep(3)
                await ch.delete()
            except Exception:
                pass
    db.set_announcement_status(ann_id, "removed")
    guild = bot.get_guild(ann["guild_id"])
    if guild and ann.get("channel_id") and ann.get("message_id"):
        ch = guild.get_channel(ann["channel_id"])
        if ch is not None:
            try:
                m = await ch.fetch_message(ann["message_id"])
                await m.delete()
            except Exception:
                pass


@app.route("/announcements/delete", methods=["POST"])
def announcement_delete():
    ann_id = int(request.form["ann_id"])
    if bot is not None and bot.loop is not None:
        # trimitem ștergerea reală pe loop-ul botului (Discord)
        asyncio.run_coroutine_threadsafe(_delete_announcement_coro(ann_id), bot.loop)
    else:
        # fără bot (dashboard rulat singur): măcar marcăm în baza de date
        db.set_announcement_status(ann_id, "removed")
    db.add_log(None, "🗑️ Anunț șters (dashboard)", f"Anunț: #{ann_id}")
    return redirect(url_for("announcements"))


def run_dashboard():
    port = int(os.getenv("DASHBOARD_PORT", "5001"))
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)


if __name__ == "__main__":
    db.init_db()
    run_dashboard()
