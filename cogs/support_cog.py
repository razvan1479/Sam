# cogs/support_cog.py — sistem de tichete stil „Ticket Tool" (ca Sir Penguin).
# Panou configurabil (titlu/descriere/culoare/banner/thumbnail) cu MAI MULTE tipuri de
# tichete (butoane). Fiecare tip: roluri care văd, categorie, mesaj de deschidere, și
# butoane bifabile (🔒 Închide / 📝 Închide cu motiv / 🙋 Revendică), + opțiuni
# (un tichet/persoană, ping la echipă). La închidere: transcript HTML în canalul de loguri.
# Config din dashboard (pagina Suport). Panoul se postează cu /ticket_panel. Membri: /add /remove.

import asyncio
import html
import io
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
import store

_STYLES = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
}


def _types(gid):
    return store.get_guild(gid).get("tk_types") or []


def _find_type(gid, tid):
    for t in _types(gid):
        if str(t.get("id")) == str(tid):
            return t
    return None


def _panel_cfg(gid):
    return store.get_guild(gid).get("tk_panel") or {}


def _color(value):
    try:
        return discord.Color(int(str(value).lstrip("#"), 16))
    except (ValueError, TypeError):
        return discord.Color(config.COLOR_PRIMARY)


async def _close_channel_later(channel, secs):
    await asyncio.sleep(secs)
    try:
        await channel.delete(reason="tichet închis")
    except discord.HTTPException:
        pass


async def build_transcript(channel) -> str:
    rows = []
    async for m in channel.history(limit=None, oldest_first=True):
        ts = m.created_at.strftime("%Y-%m-%d %H:%M")
        author = html.escape(m.author.display_name)
        content = html.escape(m.content or "")
        atts = "".join(
            f'<div class="att">📎 <a href="{a.url}">{html.escape(a.filename)}</a></div>'
            for a in m.attachments)
        if m.embeds and not content:
            content = "<i>[embed]</i>"
        rows.append(
            f'<div class="m"><span class="t">{ts}</span>'
            f'<span class="a">{author}</span><span class="c">{content}</span>{atts}</div>')
    body = "\n".join(rows) or "<p>Fără mesaje.</p>"
    return (
        "<!doctype html><html lang=ro><head><meta charset=utf-8>"
        f"<title>Transcript {html.escape(channel.name)}</title>"
        "<style>body{background:#0f1115;color:#e6e6e6;font-family:Segoe UI,Arial,sans-serif;padding:20px}"
        "h1{font-size:18px;color:#8ea1ff}.m{padding:6px 0;border-bottom:1px solid #20242c}"
        ".t{color:#7a828e;font-size:12px;margin-right:8px}.a{color:#8ea1ff;font-weight:600;margin-right:8px}"
        ".c{white-space:pre-wrap}.att a{color:#57b6ff}</style></head><body>"
        f"<h1>Transcript — {html.escape(channel.name)}</h1>{body}</body></html>"
    )


# =============================== Butoane ===============================

class OpenTicketButton(discord.ui.DynamicItem[discord.ui.Button],
                       template=config.CID_TK_OPEN + r":(?P<tid>[0-9]+)"):
    def __init__(self, ttype: dict):
        self.tid = str(ttype.get("id"))
        super().__init__(discord.ui.Button(
            label=ttype.get("label") or "Tichet",
            emoji=ttype.get("emoji") or None,
            style=_STYLES.get(ttype.get("style"), discord.ButtonStyle.primary),
            custom_id=f"{config.CID_TK_OPEN}:{ttype.get('id')}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        t = _find_type(interaction.guild_id, match["tid"]) or {"id": match["tid"], "label": "Tichet"}
        return cls(t)

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        ttype = _find_type(guild.id, self.tid)
        if not ttype:
            await interaction.response.send_message("❌ Tip de tichet inexistent.", ephemeral=True)
            return
        if ttype.get("one_per", True):
            existing = [t for t in db.list_support_tickets(guild.id)
                        if t["user_id"] == interaction.user.id and t["status"] == "open"
                        and t["kind"] == ttype.get("label")]
            if existing:
                await interaction.response.send_message(config.TK_ALREADY_OPEN, ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)
        category = guild.get_channel(ttype["category_id"]) if ttype.get("category_id") else None
        roles = [guild.get_role(r) for r in ttype.get("roles", [])]
        roles = [r for r in roles if r is not None]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, manage_channels=True),
        }
        for r in roles:
            overwrites[r] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True)

        slug = (ttype.get("label") or "tichet").lower().split()[0]
        try:
            channel = await guild.create_text_channel(
                name=f"{slug}-{interaction.user.name}", overwrites=overwrites,
                category=category, reason="tichet nou")
        except discord.Forbidden:
            await interaction.followup.send("❌ Nu am permisiunea «Manage Channels».", ephemeral=True)
            return

        tdb = db.create_support_ticket(guild.id, interaction.user.id, channel.id, ttype.get("label"))
        ping = interaction.user.mention
        if ttype.get("ping") and roles:
            ping += " " + " ".join(r.mention for r in roles)
        open_msg = (ttype.get("open_msg") or config.TK_OPEN_DEFAULT).replace(
            "{user}", interaction.user.mention).replace("{server}", guild.name)
        embed = discord.Embed(description=open_msg, color=_color(ttype.get("color")))
        await channel.send(content=ping, embed=embed, view=build_controls_view(ttype, tdb),
                           allowed_mentions=discord.AllowedMentions(users=True, roles=True))
        await interaction.followup.send(config.TK_CREATED.format(channel=channel.mention), ephemeral=True)


def _staff_or_owner(interaction, ticket):
    m = interaction.user
    if m.id == ticket["user_id"] or m.guild_permissions.administrator:
        return True
    role_ids = set()
    for t in _types(interaction.guild_id):
        role_ids.update(t.get("roles", []))
    return any(r.id in role_ids for r in m.roles)


class ClaimButton(discord.ui.DynamicItem[discord.ui.Button],
                  template=config.CID_TK_CLAIM + r":(?P<tid>[0-9]+)"):
    def __init__(self, ticket_id):
        self.ticket_id = int(ticket_id)
        super().__init__(discord.ui.Button(label=config.TK_BTN_CLAIM,
                                           style=discord.ButtonStyle.success,
                                           custom_id=f"{config.CID_TK_CLAIM}:{ticket_id}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["tid"]))

    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_support_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ Tichet inexistent.", ephemeral=True)
            return
        if interaction.user.id == ticket["user_id"] or not _staff_or_owner(interaction, ticket):
            await interaction.response.send_message(config.TK_ONLY_STAFF, ephemeral=True)
            return
        if ticket.get("claimed_by"):
            await interaction.response.send_message(
                config.TK_ALREADY_CLAIMED.format(uid=ticket["claimed_by"]), ephemeral=True)
            return
        db.set_support_claimed(ticket["id"], interaction.user.id)
        await interaction.response.send_message(
            config.TK_CLAIMED.format(user=interaction.user.mention))


class CloseButton(discord.ui.DynamicItem[discord.ui.Button],
                  template=config.CID_TK_CLOSE + r":(?P<tid>[0-9]+)"):
    def __init__(self, ticket_id):
        self.ticket_id = int(ticket_id)
        super().__init__(discord.ui.Button(label=config.TK_BTN_CLOSE,
                                           style=discord.ButtonStyle.danger,
                                           custom_id=f"{config.CID_TK_CLOSE}:{ticket_id}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["tid"]))

    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_support_ticket_by_channel(interaction.channel.id)
        if not ticket or not _staff_or_owner(interaction, ticket):
            await interaction.response.send_message(config.TK_ONLY_STAFF, ephemeral=True)
            return
        await interaction.response.send_message(
            "Sigur închizi tichetul?", view=ConfirmCloseView(ticket["id"]), ephemeral=True)


class CloseReasonButton(discord.ui.DynamicItem[discord.ui.Button],
                        template=config.CID_TK_CLOSER + r":(?P<tid>[0-9]+)"):
    def __init__(self, ticket_id):
        self.ticket_id = int(ticket_id)
        super().__init__(discord.ui.Button(label=config.TK_BTN_CLOSER,
                                           style=discord.ButtonStyle.secondary,
                                           custom_id=f"{config.CID_TK_CLOSER}:{ticket_id}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["tid"]))

    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_support_ticket_by_channel(interaction.channel.id)
        if not ticket or not _staff_or_owner(interaction, ticket):
            await interaction.response.send_message(config.TK_ONLY_STAFF, ephemeral=True)
            return
        await interaction.response.send_modal(CloseReasonModal(ticket["id"]))


class ConfirmCloseView(discord.ui.View):
    def __init__(self, ticket_id):
        super().__init__(timeout=60)
        self.ticket_id = ticket_id

    @discord.ui.button(label="Confirmă închiderea", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button):
        await interaction.response.edit_message(content="🔒 Se închide…", view=None)
        await _do_close(interaction, self.ticket_id, None)


class CloseReasonModal(discord.ui.Modal, title="Închide cu motiv"):
    motiv = discord.ui.TextInput(label="Motiv", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, ticket_id):
        super().__init__()
        self.ticket_id = ticket_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("🔒 Se închide…", ephemeral=True)
        await _do_close(interaction, self.ticket_id, str(self.motiv))


async def _do_close(interaction, ticket_id, reason):
    channel = interaction.channel
    guild = interaction.guild
    ticket = db.get_support_ticket_by_channel(channel.id)
    file = None
    try:
        doc = await build_transcript(channel)
        file = discord.File(io.BytesIO(doc.encode("utf-8")), filename=f"transcript-{channel.name}.html")
    except discord.HTTPException:
        file = None

    log_id = store.get_guild(guild.id).get("tk_log_channel_id")
    log_ch = guild.get_channel(log_id) if log_id else None
    if log_ch is not None:
        e = discord.Embed(title="🎫 Tichet închis", color=discord.Color(config.COLOR_INFO),
                          timestamp=datetime.now(timezone.utc))
        if ticket:
            e.add_field(name="Deschis de", value=f"<@{ticket['user_id']}>", inline=True)
            e.add_field(name="Tip", value=ticket.get("kind") or "—", inline=True)
            if ticket.get("claimed_by"):
                e.add_field(name="Revendicat de", value=f"<@{ticket['claimed_by']}>", inline=True)
        e.add_field(name="Închis de", value=interaction.user.mention, inline=True)
        if reason:
            e.add_field(name="Motiv", value=reason[:1000], inline=False)
        try:
            await log_ch.send(embed=e, file=file)
        except discord.HTTPException:
            pass

    if ticket:
        db.set_support_ticket_status(ticket["id"], "closed")
        if reason:
            db.set_support_reason(ticket["id"], reason)
    try:
        await channel.send(config.TK_CLOSING)
    except discord.HTTPException:
        pass
    asyncio.create_task(_close_channel_later(channel, 4))


def build_controls_view(ttype, ticket_db_id):
    v = discord.ui.View(timeout=None)
    if ttype.get("claim"):
        v.add_item(ClaimButton(ticket_db_id))
    if ttype.get("close", True):
        v.add_item(CloseButton(ticket_db_id))
    if ttype.get("close_reason"):
        v.add_item(CloseReasonButton(ticket_db_id))
    return v


def make_panel_view(gid):
    v = discord.ui.View(timeout=None)
    for t in _types(gid)[:25]:
        v.add_item(OpenTicketButton(t))
    return v


# =============================== Cog ===============================

class Support(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_dynamic_items(OpenTicketButton, ClaimButton, CloseButton, CloseReasonButton)

    async def post_panel(self, channel):
        gid = channel.guild.id
        cfg = _panel_cfg(gid)
        embed = discord.Embed(
            title=cfg.get("title") or config.TK_PANEL_TITLE_DEFAULT,
            description=cfg.get("description") or config.TK_PANEL_DESC_DEFAULT,
            color=_color(cfg.get("color")))
        if cfg.get("banner"):
            embed.set_image(url=cfg["banner"])
        if cfg.get("thumbnail"):
            embed.set_thumbnail(url=cfg["thumbnail"])
        msg = await channel.send(embed=embed, view=make_panel_view(gid))
        store.set_guild_value(gid, "tk_panel_channel_id", channel.id)
        store.set_guild_value(gid, "tk_panel_message_id", msg.id)

    @app_commands.command(name="ticket_panel", description="Postează panoul de tichete")
    @app_commands.default_permissions(administrator=True)
    async def ticket_panel(self, interaction: discord.Interaction):
        if not _types(interaction.guild_id):
            await interaction.response.send_message(config.TK_NO_TYPES, ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.post_panel(interaction.channel)
        await interaction.followup.send("✅ Panou postat.", ephemeral=True)

    @app_commands.command(name="add", description="Adaugă un membru în tichetul curent")
    @app_commands.default_permissions(manage_channels=True)
    async def add_member(self, interaction: discord.Interaction, membru: discord.Member):
        if not db.get_support_ticket_by_channel(interaction.channel.id):
            await interaction.response.send_message("❌ Nu ești într-un tichet.", ephemeral=True)
            return
        await interaction.channel.set_permissions(
            membru, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"✅ {membru.mention} adăugat.", ephemeral=True)

    @app_commands.command(name="remove", description="Scoate un membru din tichetul curent")
    @app_commands.default_permissions(manage_channels=True)
    async def remove_member(self, interaction: discord.Interaction, membru: discord.Member):
        if not db.get_support_ticket_by_channel(interaction.channel.id):
            await interaction.response.send_message("❌ Nu ești într-un tichet.", ephemeral=True)
            return
        await interaction.channel.set_permissions(membru, overwrite=None)
        await interaction.response.send_message(f"✅ {membru.mention} scos.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Support(bot))
