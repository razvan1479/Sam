# db.py — stratul de bază de date (SQLite) pentru datele structurate ale marketplace-ului.
# Setările (canal, mesaj panou) rămân în store.py (JSON). Aici stau anunțurile, ticketele, userii etc.

import os
import time
import sqlite3

import config

_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "marketplace.db")

# Toate coloanele există indiferent de cum arată modalul de creare — stratul de date e independent de UI.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS announcements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id      INTEGER NOT NULL,
    author_id     INTEGER NOT NULL,
    server_from   TEXT,
    server_to     TEXT,
    offer         TEXT,
    want          TEXT,
    ratio         TEXT,
    details       TEXT,
    status        TEXT NOT NULL DEFAULT 'available',   -- available | finished | removed
    channel_id    INTEGER,
    message_id    INTEGER,
    created_at    INTEGER NOT NULL,
    last_bump_at  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ann_guild_status ON announcements(guild_id, status);
CREATE INDEX IF NOT EXISTS idx_ann_author       ON announcements(author_id);

CREATE TABLE IF NOT EXISTS tickets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id        INTEGER NOT NULL,
    announcement_id INTEGER NOT NULL,
    buyer_id        INTEGER NOT NULL,
    author_id       INTEGER NOT NULL,
    channel_id      INTEGER,
    status          TEXT NOT NULL DEFAULT 'open',  -- open | accepted | refused | closed | finalized
    created_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ticket_ann   ON tickets(announcement_id, status);
CREATE INDEX IF NOT EXISTS idx_ticket_buyer ON tickets(guild_id, buyer_id, announcement_id, status);

CREATE TABLE IF NOT EXISTS blocks (
    guild_id        INTEGER NOT NULL,
    author_id       INTEGER NOT NULL,
    blocked_user_id INTEGER NOT NULL,
    created_at      INTEGER NOT NULL,
    PRIMARY KEY (guild_id, author_id, blocked_user_id)
);

CREATE TABLE IF NOT EXISTS user_stats (
    guild_id               INTEGER NOT NULL,
    user_id                INTEGER NOT NULL,
    completed              INTEGER NOT NULL DEFAULT 0,
    cancelled              INTEGER NOT NULL DEFAULT 0,
    confirmed_reports      INTEGER NOT NULL DEFAULT 0,
    announcements_created  INTEGER NOT NULL DEFAULT 0,
    announcements_finished INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS global_blacklist (
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    reason     TEXT,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    ticket_id   INTEGER,
    reporter_id INTEGER NOT NULL,
    reported_id INTEGER NOT NULL,
    reason      TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending | confirmed | rejected
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reports_reported ON reports(guild_id, reported_id, status);

CREATE TABLE IF NOT EXISTS logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER,
    action     TEXT NOT NULL,
    detail     TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_id ON logs(id DESC);

CREATE TABLE IF NOT EXISTS calendar_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    date        TEXT NOT NULL,      -- YYYY-MM-DD
    time        TEXT,               -- HH:MM sau NULL
    description TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cal_guild_date ON calendar_events(guild_id, date);

CREATE TABLE IF NOT EXISTS promoters (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    name       TEXT NOT NULL,
    channel_id INTEGER,
    created_at INTEGER NOT NULL,
    UNIQUE(guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS promoter_votes (
    promoter_id INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    value       INTEGER NOT NULL,   -- 1 = like, -1 = dislike
    updated_at  INTEGER NOT NULL,
    PRIMARY KEY (promoter_id, user_id)
);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")   # scrieri concurente mai bune
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Creează tabelele dacă nu există. Se apelează o dată, la pornirea botului."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)


# ---------- Anunțuri ----------

def create_announcement(guild_id, author_id, *, server_from, server_to,
                        offer, want, ratio, details) -> int:
    """Inserează un anunț nou și întoarce ID-ul lui unic (auto-incrementat)."""
    now = int(time.time())
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO announcements
               (guild_id, author_id, server_from, server_to, offer, want, ratio, details, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (guild_id, author_id, server_from, server_to, offer, want, ratio, details, now),
        )
        return cur.lastrowid


def set_announcement_message(ann_id, channel_id, message_id) -> None:
    """Salvează unde a fost postat embed-ul anunțului (canal + mesaj)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE announcements SET channel_id=?, message_id=? WHERE id=?",
            (channel_id, message_id, ann_id),
        )


def get_announcement(ann_id) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM announcements WHERE id=?", (ann_id,)).fetchone()
        return dict(row) if row else None


# ---------- Tickete ----------

def has_active_ticket(guild_id, announcement_id, buyer_id) -> bool:
    """Are userul deja un ticket ACTIV (open/accepted) pentru acest anunț?"""
    with _connect() as conn:
        row = conn.execute(
            """SELECT 1 FROM tickets
               WHERE guild_id=? AND announcement_id=? AND buyer_id=?
                 AND status IN ('open','accepted') LIMIT 1""",
            (guild_id, announcement_id, buyer_id),
        ).fetchone()
        return row is not None


def create_ticket(guild_id, announcement_id, buyer_id, author_id, channel_id) -> int:
    now = int(time.time())
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO tickets (guild_id, announcement_id, buyer_id, author_id, channel_id, created_at)
               VALUES (?,?,?,?,?,?)""",
            (guild_id, announcement_id, buyer_id, author_id, channel_id, now),
        )
        return cur.lastrowid


def get_ticket(ticket_id) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
        return dict(row) if row else None


def set_ticket_status(ticket_id, status) -> None:
    with _connect() as conn:
        conn.execute("UPDATE tickets SET status=? WHERE id=?", (status, ticket_id))


# ---------- Blocări ----------

def is_blocked(guild_id, author_id, blocked_user_id) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM blocks WHERE guild_id=? AND author_id=? AND blocked_user_id=? LIMIT 1",
            (guild_id, author_id, blocked_user_id),
        ).fetchone()
        return row is not None


def add_block(guild_id, author_id, blocked_user_id) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO blocks (guild_id, author_id, blocked_user_id, created_at)
               VALUES (?,?,?,?)""",
            (guild_id, author_id, blocked_user_id, now),
        )


def remove_block(guild_id, author_id, blocked_user_id) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM blocks WHERE guild_id=? AND author_id=? AND blocked_user_id=?",
            (guild_id, author_id, blocked_user_id),
        )


# ---------- Statistici utilizator ----------

def get_user_stats(guild_id, user_id) -> dict:
    """Întoarce statisticile unui user (zerouri dacă nu are încă rând)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM user_stats WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        ).fetchone()
    if row:
        return dict(row)
    return {
        "guild_id": guild_id, "user_id": user_id,
        "completed": 0, "cancelled": 0, "confirmed_reports": 0,
        "announcements_created": 0, "announcements_finished": 0,
    }


def update_announcement(ann_id, *, server_from, server_to, offer, want, ratio) -> None:
    """Actualizează conținutul unui anunț (folosit la Editează)."""
    with _connect() as conn:
        conn.execute(
            """UPDATE announcements
               SET server_from=?, server_to=?, offer=?, want=?, ratio=?
               WHERE id=?""",
            (server_from, server_to, offer, want, ratio, ann_id),
        )


def bump_announcement(ann_id, message_id, ts) -> None:
    """Actualizează mesajul și momentul ultimei ridicări (folosit la Ridică)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE announcements SET message_id=?, last_bump_at=? WHERE id=?",
            (message_id, ts, ann_id),
        )


def set_announcement_status(ann_id, status) -> None:
    with _connect() as conn:
        conn.execute("UPDATE announcements SET status=? WHERE id=?", (status, ann_id))


def get_active_tickets_for_announcement(announcement_id, exclude_ticket_id=None) -> list:
    """Ticketele încă active (open/accepted) pentru un anunț, opțional excluzând unul."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE announcement_id=? AND status IN ('open','accepted')",
            (announcement_id,),
        ).fetchall()
    return [dict(r) for r in rows if exclude_ticket_id is None or r["id"] != exclude_ticket_id]


_STAT_FIELDS = {"completed", "cancelled", "confirmed_reports",
                "announcements_created", "announcements_finished"}


def increment_user_stat(guild_id, user_id, field, amount=1) -> None:
    """Crește un contor din user_stats (creează rândul dacă nu există)."""
    if field not in _STAT_FIELDS:
        raise ValueError(f"camp de statistica invalid: {field}")
    with _connect() as conn:
        conn.execute(
            f"""INSERT INTO user_stats (guild_id, user_id, {field}) VALUES (?,?,?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET {field}={field}+?""",
            (guild_id, user_id, amount, amount),
        )


# ---------- Blacklist global (staff) ----------

def add_global_block(guild_id, user_id, reason=None) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """INSERT INTO global_blacklist (guild_id, user_id, reason, created_at)
               VALUES (?,?,?,?)
               ON CONFLICT(guild_id, user_id) DO UPDATE SET reason=excluded.reason""",
            (guild_id, user_id, reason, now),
        )


def remove_global_block(guild_id, user_id) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM global_blacklist WHERE guild_id=? AND user_id=?",
                     (guild_id, user_id))


def is_global_blocked(guild_id, user_id) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM global_blacklist WHERE guild_id=? AND user_id=? LIMIT 1",
            (guild_id, user_id),
        ).fetchone()
        return row is not None


# ---------- Statistici agregate ----------

def get_marketplace_stats(guild_id) -> dict:
    with _connect() as conn:
        def one(q):
            return conn.execute(q, (guild_id,)).fetchone()[0]
        return {
            "ann_total":     one("SELECT COUNT(*) FROM announcements WHERE guild_id=?"),
            "ann_available": one("SELECT COUNT(*) FROM announcements WHERE guild_id=? AND status='available'"),
            "ann_finished":  one("SELECT COUNT(*) FROM announcements WHERE guild_id=? AND status='finalized'"),
            "tickets_total": one("SELECT COUNT(*) FROM tickets WHERE guild_id=?"),
            "tickets_open":  one("SELECT COUNT(*) FROM tickets WHERE guild_id=? AND status IN ('open','accepted')"),
            "blocks":        one("SELECT COUNT(*) FROM blocks WHERE guild_id=?"),
            "blacklisted":   one("SELECT COUNT(*) FROM global_blacklist WHERE guild_id=?"),
        }


# ---------- Raportări ----------

def create_report(guild_id, ticket_id, reporter_id, reported_id, reason) -> int:
    now = int(time.time())
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO reports (guild_id, ticket_id, reporter_id, reported_id, reason, created_at)
               VALUES (?,?,?,?,?,?)""",
            (guild_id, ticket_id, reporter_id, reported_id, reason, now),
        )
        return cur.lastrowid


def get_report(report_id) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
        return dict(row) if row else None


def set_report_status(report_id, status) -> None:
    with _connect() as conn:
        conn.execute("UPDATE reports SET status=? WHERE id=?", (status, report_id))


# ---------- Citiri pentru dashboard ----------

def get_overview_stats() -> dict:
    with _connect() as conn:
        def one(q):
            return conn.execute(q).fetchone()[0]
        return {
            "ann_total":         one("SELECT COUNT(*) FROM announcements"),
            "ann_available":     one("SELECT COUNT(*) FROM announcements WHERE status='available'"),
            "ann_finished":      one("SELECT COUNT(*) FROM announcements WHERE status='finalized'"),
            "tickets_total":     one("SELECT COUNT(*) FROM tickets"),
            "tickets_open":      one("SELECT COUNT(*) FROM tickets WHERE status IN ('open','accepted')"),
            "reports_total":     one("SELECT COUNT(*) FROM reports"),
            "reports_confirmed": one("SELECT COUNT(*) FROM reports WHERE status='confirmed'"),
            "blacklisted":       one("SELECT COUNT(*) FROM global_blacklist"),
        }


def list_announcements(limit=200) -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM announcements ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def list_tickets(limit=200) -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def list_blacklist() -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM global_blacklist ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- Loguri (toate acțiunile, pentru dashboard) ----------

_last_prune_day = None


def add_log(guild_id, action, detail=None) -> None:
    global _last_prune_day
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO logs (guild_id, action, detail, created_at) VALUES (?,?,?,?)",
            (guild_id, action, detail, now),
        )
        # Curățare automată: o singură dată pe zi (la primul log al zilei),
        # șterge logurile mai vechi de LOG_KEEP_DAYS zile. Fără proces separat.
        day = now // 86400
        if _last_prune_day != day:
            _last_prune_day = day
            cutoff = now - config.LOG_KEEP_DAYS * 86400
            conn.execute("DELETE FROM logs WHERE created_at < ?", (cutoff,))


def list_logs(limit=300) -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- Calendar (evenimente) ----------

def add_event(guild_id, date, event_time, description) -> int:
    now = int(time.time())
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO calendar_events (guild_id, date, time, description, created_at)
               VALUES (?,?,?,?,?)""",
            (guild_id, date, event_time, description, now),
        )
        return cur.lastrowid


def get_event(event_id, guild_id) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM calendar_events WHERE id=? AND guild_id=?", (event_id, guild_id)
        ).fetchone()
        return dict(row) if row else None


def delete_event(event_id, guild_id) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM calendar_events WHERE id=? AND guild_id=?", (event_id, guild_id)
        )
        return cur.rowcount > 0


def events_on(guild_id, date) -> list:
    """Evenimentele dintr-o zi anume; cele cu oră primele, apoi cele fără oră."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT * FROM calendar_events WHERE guild_id=? AND date=?
               ORDER BY (time IS NULL), time""",
            (guild_id, date),
        ).fetchall()
    return [dict(r) for r in rows]


def upcoming_events(guild_id, after_date, limit=10) -> list:
    """Evenimentele viitoare (dată strict mai mare decât after_date)."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT * FROM calendar_events WHERE guild_id=? AND date > ?
               ORDER BY date, (time IS NULL), time LIMIT ?""",
            (guild_id, after_date, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def list_events(guild_id, from_date=None, limit=50) -> list:
    """Toate evenimentele (opțional de la o dată încolo)."""
    with _connect() as conn:
        if from_date:
            rows = conn.execute(
                """SELECT * FROM calendar_events WHERE guild_id=? AND date >= ?
                   ORDER BY date, (time IS NULL), time LIMIT ?""",
                (guild_id, from_date, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM calendar_events WHERE guild_id=?
                   ORDER BY date, (time IS NULL), time LIMIT ?""",
                (guild_id, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def delete_past_events(guild_id, today) -> int:
    """Șterge evenimentele mai vechi decât ziua curentă. Întoarce câte a șters."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM calendar_events WHERE guild_id=? AND date < ?", (guild_id, today)
        )
        return cur.rowcount


# ---------- Leaderboard promoteri ----------

def add_promoter(guild_id, user_id, name, channel_id) -> int:
    now = int(time.time())
    with _connect() as conn:
        cur = conn.execute(
            """INSERT INTO promoters (guild_id, user_id, name, channel_id, created_at)
               VALUES (?,?,?,?,?)""",
            (guild_id, user_id, name, channel_id, now),
        )
        return cur.lastrowid


def get_promoter(promoter_id) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM promoters WHERE id=?", (promoter_id,)).fetchone()
        return dict(row) if row else None


def get_promoter_by_user(guild_id, user_id) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM promoters WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        ).fetchone()
        return dict(row) if row else None


def remove_promoter(promoter_id) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM promoter_votes WHERE promoter_id=?", (promoter_id,))
        conn.execute("DELETE FROM promoters WHERE id=?", (promoter_id,))


def list_promoters_sorted(guild_id) -> list:
    """Toți promoterii cu likes/dislikes, sortați după scor (like-dislike) desc."""
    with _connect() as conn:
        rows = conn.execute(
            """SELECT p.*,
                      COALESCE(SUM(CASE WHEN v.value=1  THEN 1 ELSE 0 END), 0) AS likes,
                      COALESCE(SUM(CASE WHEN v.value=-1 THEN 1 ELSE 0 END), 0) AS dislikes
               FROM promoters p
               LEFT JOIN promoter_votes v ON v.promoter_id = p.id
               WHERE p.guild_id=?
               GROUP BY p.id""",
            (guild_id,),
        ).fetchall()
    promoters = [dict(r) for r in rows]
    promoters.sort(key=lambda p: (-(p["likes"] - p["dislikes"]), -p["likes"], p["name"].lower()))
    return promoters


def get_vote(promoter_id, user_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT value FROM promoter_votes WHERE promoter_id=? AND user_id=?",
            (promoter_id, user_id),
        ).fetchone()
        return row["value"] if row else None


def set_vote(promoter_id, user_id, value) -> None:
    now = int(time.time())
    with _connect() as conn:
        conn.execute(
            """INSERT INTO promoter_votes (promoter_id, user_id, value, updated_at)
               VALUES (?,?,?,?)
               ON CONFLICT(promoter_id, user_id) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (promoter_id, user_id, value, now),
        )


# ---------- Releu anonim vânzător (DM <-> ticket) ----------

def get_ticket_by_channel(channel_id) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM tickets WHERE channel_id=? ORDER BY id DESC LIMIT 1", (channel_id,)
        ).fetchone()
        return dict(row) if row else None


def get_accepted_tickets_for_seller(seller_id) -> list:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM tickets WHERE author_id=? AND status='accepted' ORDER BY id DESC",
            (seller_id,),
        ).fetchall()
    return [dict(r) for r in rows]
