# cogs/calendar_cog.py — FUNCȚIA 2: calendar lunar într-un mesaj fixat + notificări @everyone.
# Fus orar: Europe/Bucharest (folosim zoneinfo din standard, fără pytz).
# Datele stau în aceeași bază SQLite (db.py); setările în store.py.

import calendar as pycalendar
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

import db
import store

TZ = ZoneInfo("Europe/Bucharest")

# Luni pe primul loc (L M M J V S D)
WEEK_HEADER = "L  M  M  J  V  S  D"
MONTHS_RO = ["Ianuarie", "Februarie", "Martie", "Aprilie", "Mai", "Iunie",
             "Iulie", "August", "Septembrie", "Octombrie", "Noiembrie", "Decembrie"]
MONTHS_RO_SHORT = ["Ian", "Feb", "Mar", "Apr", "Mai", "Iun",
                   "Iul", "Aug", "Sep", "Oct", "Noi", "Dec"]


# =========================================================
#  Construirea textului
# =========================================================

def build_calendar_text(year: int, month: int, highlight_day: int) -> str:
    """Grila lunii, cu ziua curentă în [paranteze]. Se afișează într-un bloc de cod (monospace)."""
    weeks = pycalendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    lines = [WEEK_HEADER]
    for week in weeks:
        cells = []
        for d in week:
            if d == 0:
                cells.append("  ")            # zi din afara lunii
            elif d == highlight_day:
                cells.append(f"[{d}]")        # ziua curentă
            else:
                cells.append(f"{d:2d}")
        lines.append(" ".join(cells))
    return "\n".join(lines)


def _fmt_today(e: dict) -> str:
    if e.get("time"):
        return f"• {e['description']} {e['time']}"
    return f"• {e['description']}"


def _fmt_upcoming(e: dict) -> str:
    # "08 Aug • Lansare versiune"
    y, m, d = e["date"].split("-")
    return f"{int(d):02d} {MONTHS_RO_SHORT[int(m) - 1]} • {e['description']}"


def build_events_section(guild_id: int, today: str) -> str:
    today_events = db.events_on(guild_id, today)
    upcoming = db.upcoming_events(guild_id, today)

    parts = []
    if today_events:
        parts.append("📍 **Astăzi**\n" + "\n".join(_fmt_today(e) for e in today_events))
    if upcoming:
        parts.append("📌 **Următoarele evenimente**\n" + "\n".join(_fmt_upcoming(e) for e in upcoming))
    if not today_events and not upcoming:
        parts.append("✅ Nu există evenimente programate.")
    return "\n\n".join(parts)


def build_full_content(guild_id: int, now: datetime) -> str:
    title = f"📅 **{MONTHS_RO[now.month - 1]} {now.year}**"
    grid = build_calendar_text(now.year, now.month, now.day)
    events = build_events_section(guild_id, now.strftime("%Y-%m-%d"))
    return f"{title}\n```\n{grid}\n```\n{events}"


def build_notification(guild_id: int, today: str) -> str:
    lines = "\n".join(_fmt_today(e) for e in db.events_on(guild_id, today))
    return f"@everyone\n\n📅 **Evenimentele de astăzi**\n\n{lines}"


# =========================================================
#  Cog
# =========================================================

class Calendar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.ticker.start()

    async def cog_unload(self):
        self.ticker.cancel()

    # ---- construiește / actualizează mesajul fixat ----
    async def refresh_calendar(self, guild: discord.Guild, channel: discord.TextChannel = None):
        s = store.get_guild(guild.id)
        if channel is None:
            ch_id = s.get("calendar_channel_id")
            channel = guild.get_channel(ch_id) if ch_id else None
        if channel is None:
            return

        now = datetime.now(TZ)
        content = build_full_content(guild.id, now)

        msg = None
        msg_id = s.get("calendar_message_id")
        if msg_id:
            try:
                msg = await channel.fetch_message(msg_id)
            except discord.NotFound:
                msg = None

        if msg is None:
            msg = await channel.send(content)
            store.set_guild_value(guild.id, "calendar_message_id", msg.id)
            try:
                await msg.pin()
            except discord.HTTPException:
                pass
        else:
            try:
                await msg.edit(content=content)
            except discord.HTTPException:
                pass

    # ---- bucla care rulează în fiecare minut ----
    @tasks.loop(minutes=1)
    async def ticker(self):
        now = datetime.now(TZ)
        today = now.strftime("%Y-%m-%d")

        for guild in list(self.bot.guilds):
            s = store.get_guild(guild.id)
            ch_id = s.get("calendar_channel_id")
            if not ch_id:
                continue
            channel = guild.get_channel(ch_id)
            if channel is None:
                continue

            # 1) La miezul nopții: curățăm trecutul, ștergem notificarea de ieri, reîmprospătăm
            if now.hour == 0 and s.get("last_cleanup_date") != today:
                db.delete_past_events(guild.id, today)
                old_notif = s.get("notify_message_id")
                if old_notif:
                    try:
                        m = await channel.fetch_message(old_notif)
                        await m.delete()
                    except discord.HTTPException:
                        pass
                store.set_guild_value(guild.id, "notify_message_id", None)
                store.set_guild_value(guild.id, "last_cleanup_date", today)
                await self.refresh_calendar(guild, channel)

            # 2) Actualizare orară a calendarului (la schimbarea orei / la pornire)
            hour_key = now.strftime("%Y-%m-%d %H")
            if s.get("last_calendar_hour") != hour_key:
                await self.refresh_calendar(guild, channel)
                store.set_guild_value(guild.id, "last_calendar_hour", hour_key)

            # 3) Notificarea @everyone la ora configurată (un singur mesaj pe zi)
            notify_hour = s.get("notify_hour", "08:00")
            if now.strftime("%H:%M") == notify_hour and s.get("notify_sent_date") != today:
                if db.events_on(guild.id, today):
                    try:
                        msg = await channel.send(
                            build_notification(guild.id, today),
                            allowed_mentions=discord.AllowedMentions(everyone=True),
                        )
                        store.set_guild_value(guild.id, "notify_message_id", msg.id)
                    except discord.HTTPException:
                        pass
                store.set_guild_value(guild.id, "notify_sent_date", today)

    @ticker.before_loop
    async def _before(self):
        await self.bot.wait_until_ready()

    # =========================================================
    #  Comenzi slash
    # =========================================================

    @app_commands.command(name="adauga", description="Adaugă un eveniment în calendar")
    @app_commands.describe(data="Data YYYY-MM-DD", descriere="Descrierea evenimentului",
                           ora="Ora HH:MM (opțional)")
    @app_commands.default_permissions(administrator=True)
    async def adauga(self, interaction: discord.Interaction,
                     data: str, descriere: str, ora: str = None):
        try:
            datetime.strptime(data, "%Y-%m-%d")
        except ValueError:
            await interaction.response.send_message("❌ Data trebuie să fie YYYY-MM-DD.", ephemeral=True)
            return
        if ora:
            try:
                datetime.strptime(ora, "%H:%M")
            except ValueError:
                await interaction.response.send_message("❌ Ora trebuie să fie HH:MM.", ephemeral=True)
                return

        eid = db.add_event(interaction.guild_id, data, ora, descriere)
        await self.refresh_calendar(interaction.guild)
        await interaction.response.send_message(
            f"✅ Eveniment adăugat (#{eid}): **{descriere}** pe {data}" + (f" la {ora}" if ora else ""),
            ephemeral=True,
        )

    @app_commands.command(name="sterge", description="Șterge un eveniment după ID")
    @app_commands.describe(id="ID-ul evenimentului (din /lista)")
    @app_commands.default_permissions(administrator=True)
    async def sterge(self, interaction: discord.Interaction, id: int):
        if db.delete_event(id, interaction.guild_id):
            await self.refresh_calendar(interaction.guild)
            await interaction.response.send_message(f"✅ Evenimentul #{id} a fost șters.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nu există un eveniment cu acest ID.", ephemeral=True)

    @app_commands.command(name="lista", description="Arată evenimentele programate")
    async def lista(self, interaction: discord.Interaction):
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        events = db.list_events(interaction.guild_id, from_date=today)
        if not events:
            await interaction.response.send_message("✅ Nu există evenimente programate.", ephemeral=True)
            return
        lines = []
        for e in events:
            when = e["date"] + (f" {e['time']}" if e.get("time") else "")
            lines.append(f"`#{e['id']}` — {when} • {e['description']}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @app_commands.command(name="seteaza_canal", description="Setează canalul calendarului")
    @app_commands.describe(canal="Canalul în care stă mesajul cu calendarul")
    @app_commands.default_permissions(administrator=True)
    async def seteaza_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        # canal nou → uităm mesajul vechi și postăm unul nou acolo
        store.set_guild_value(interaction.guild_id, "calendar_channel_id", canal.id)
        store.set_guild_value(interaction.guild_id, "calendar_message_id", None)
        store.set_guild_value(interaction.guild_id, "last_calendar_hour", None)
        await self.refresh_calendar(interaction.guild, canal)
        await interaction.response.send_message(
            f"✅ Calendarul a fost setat în {canal.mention}.", ephemeral=True)

    @app_commands.command(name="seteaza_ora_notificare", description="Setează ora notificării zilnice (HH:MM)")
    @app_commands.describe(ora="Ora la care se trimite @everyone (HH:MM)")
    @app_commands.default_permissions(administrator=True)
    async def seteaza_ora_notificare(self, interaction: discord.Interaction, ora: str):
        try:
            datetime.strptime(ora, "%H:%M")
        except ValueError:
            await interaction.response.send_message("❌ Ora trebuie să fie HH:MM.", ephemeral=True)
            return
        store.set_guild_value(interaction.guild_id, "notify_hour", ora)
        await interaction.response.send_message(f"✅ Ora notificării: **{ora}**.", ephemeral=True)

    @app_commands.command(name="regenereaza", description="Recreează mesajul cu calendarul")
    @app_commands.default_permissions(administrator=True)
    async def regenereaza(self, interaction: discord.Interaction):
        s = store.get_guild(interaction.guild_id)
        ch_id = s.get("calendar_channel_id")
        if not ch_id:
            await interaction.response.send_message(
                "❌ Setează întâi canalul cu `/seteaza_canal`.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(ch_id)
        if channel is None:
            await interaction.response.send_message(
                "❌ Canalul salvat nu mai există. Rulează din nou `/seteaza_canal`.", ephemeral=True)
            return
        # ștergem mesajul vechi dacă există, apoi postăm unul nou
        old_id = s.get("calendar_message_id")
        if old_id:
            try:
                old = await channel.fetch_message(old_id)
                await old.delete()
            except discord.HTTPException:
                pass
        store.set_guild_value(interaction.guild_id, "calendar_message_id", None)
        await self.refresh_calendar(interaction.guild, channel)
        await interaction.response.send_message("✅ Calendar regenerat.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Calendar(bot))
