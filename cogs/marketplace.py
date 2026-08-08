# cogs/marketplace.py — FUNCȚIA 1 (panou) + FUNCȚIA 2 (creare anunț) + FUNCȚIA 3 (Contactează)

import asyncio
import time
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
import store

# cooldown anti-spam la Contactează: user_id -> timestamp-ul ultimei creări de ticket (în memorie)
_contact_cd: dict[int, float] = {}


# =========================================================
#  EMBED-URI
# =========================================================

def build_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title=config.PANEL_TITLE,
        description=config.PANEL_DESCRIPTION,
        color=config.COLOR_INFO,
    )
    embed.set_footer(text=config.PANEL_FOOTER)
    return embed


def build_announcement_embed(ann: dict) -> discord.Embed:
    """Embed-ul unui anunț. ANONIM — nu afișează nimic despre autor.
    Doar câmpurile completate apar, cu spațiere între secțiuni pentru lizibilitate."""
    blocks = []

    servers = []
    if ann.get("server_from"):
        servers.append(f"**{config.F_SERVER_FROM}:** {ann['server_from']}")
    if ann.get("server_to"):
        servers.append(f"**{config.F_SERVER_TO}:** {ann['server_to']}")
    if servers:
        blocks.append("\n".join(servers))

    if ann.get("offer"):
        blocks.append(f"**{config.F_OFFER}:**\n{ann['offer']}")
    if ann.get("want"):
        blocks.append(f"**{config.F_WANT}:**\n{ann['want']}")

    body = "\n\n".join(blocks)
    description = config.ANN_DIVIDER + (("\n\n" + body) if body else "")

    embed = discord.Embed(
        title=f"{config.EMOJI_ANNOUNCE} " + config.ANN_TITLE.format(id=ann["id"]),
        description=description,
        color=config.COLOR_PRIMARY,
    )
    embed.set_footer(text=config.ANN_FOOTER)
    embed.timestamp = datetime.fromtimestamp(ann["created_at"], tz=timezone.utc)
    return embed


def _relay_body(message: discord.Message) -> str:
    """Textul unui mesaj + link-urile atașamentelor (CDN-ul nu dezvăluie identitatea)."""
    body = (message.content or "").strip()
    if message.attachments:
        body = (body + "\n" + "\n".join(a.url for a in message.attachments)).strip()
    return body


def build_dm_embed(buyer, ann_id: int, ticket_id: int, stats: dict) -> discord.Embed:
    """Embed-ul trimis autorului când cineva îi contactează anunțul.
    ANONIM: nu arată cine e cumpărătorul — doar reputația lui obiectivă."""
    e = discord.Embed(title=config.DM_TITLE.format(ann_id=ann_id), color=config.COLOR_INFO)
    e.description = config.DM_ANON_NOTE
    e.add_field(name=config.DM_F_COMPLETED, value=str(stats["completed"]), inline=True)
    e.add_field(name=config.DM_F_CANCELLED, value=str(stats["cancelled"]), inline=True)
    e.add_field(name=config.DM_F_REPORTS, value=str(stats["confirmed_reports"]), inline=True)
    e.add_field(name=config.DM_F_TICKET, value=str(ticket_id), inline=False)
    return e


def _humanize_duration(delta_seconds: int) -> str:
    """Transformă o durată în text românesc: «1 an, 3 luni» / «24 zile»."""
    days = int(delta_seconds // 86400)
    years, rem = divmod(days, 365)
    months, d = divmod(rem, 30)
    parts = []
    if years:
        parts.append(f"{years} an" + ("i" if years > 1 else ""))
    if months:
        parts.append(f"{months} " + ("lună" if months == 1 else "luni"))
    if not years and not months:
        parts.append(f"{d} " + ("zi" if d == 1 else "zile"))
    return ", ".join(parts) if parts else "mai puțin de o zi"


def build_profile_embed(user, stats: dict) -> discord.Embed:
    """Profil Marketplace — doar informații obiective (fără trust score / badge-uri)."""
    e = discord.Embed(title="📄 " + config.PROFILE_TITLE, color=config.COLOR_INFO)
    e.set_thumbnail(url=user.display_avatar.url)
    e.add_field(name=config.PROFILE_F_USER, value=user.mention, inline=False)
    e.add_field(name=config.PROFILE_F_ID, value=str(user.id), inline=True)
    e.add_field(name=config.PROFILE_F_ACCOUNT,
                value=f"<t:{int(user.created_at.timestamp())}:D>", inline=True)
    joined = getattr(user, "joined_at", None)
    e.add_field(name=config.PROFILE_F_JOINED,
                value=(f"<t:{int(joined.timestamp())}:D>" if joined else "necunoscut"), inline=True)
    e.add_field(name=config.PROFILE_F_TIME,
                value=(_humanize_duration(int(time.time() - joined.timestamp())) if joined else "necunoscut"),
                inline=True)
    e.add_field(name=config.PROFILE_STATS, value="\u200b", inline=False)  # separator
    e.add_field(name=config.PROFILE_F_COMPLETED, value=str(stats["completed"]), inline=True)
    e.add_field(name=config.PROFILE_F_CANCELLED, value=str(stats["cancelled"]), inline=True)
    e.add_field(name=config.PROFILE_F_REPORTS, value=str(stats["confirmed_reports"]), inline=True)
    return e


async def _close_channel_later(channel: discord.TextChannel, delay: int) -> None:
    """Șterge un canal de ticket după `delay` secunde."""
    await asyncio.sleep(delay)
    try:
        await channel.delete(reason="Ticket închis")
    except discord.HTTPException:
        pass


async def log_action(guild, title: str, fields: dict = None, color: int = None,
                     success: bool = False) -> None:
    """Scrie MEREU acțiunea în baza de date (pentru dashboard).
    Pe Discord trimite DOAR acțiunile de succes (success=True)."""
    detail = " · ".join(f"{k}: {v}" for k, v in (fields or {}).items())
    db.add_log(guild.id if guild else None, title, detail or None)

    if not success:
        return
    if guild is None:
        return
    log_id = store.get_guild(guild.id).get("log_channel_id")
    if not log_id:
        return
    channel = guild.get_channel(log_id)
    if channel is None:
        return
    embed = discord.Embed(title=title, color=color or config.COLOR_INFO,
                          timestamp=discord.utils.utcnow())
    for name, value in (fields or {}).items():
        embed.add_field(name=name, value=str(value), inline=True)
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


# =========================================================
#  BUTOANELE DE PE ANUNȚ (persistente, cu ID-ul anunțului în custom_id)
# =========================================================

class ContactButton(discord.ui.DynamicItem[discord.ui.Button],
                    template=config.CID_CONTACT + r":(?P<ann_id>[0-9]+)"):
    def __init__(self, ann_id: int):
        self.ann_id = ann_id
        super().__init__(discord.ui.Button(
            label=config.BTN_CONTACT, emoji=config.EMOJI_CONTACT,
            style=discord.ButtonStyle.primary,
            custom_id=f"{config.CID_CONTACT}:{ann_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["ann_id"]))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        ann = db.get_announcement(self.ann_id)
        if not ann or ann["status"] != "available":
            await interaction.followup.send(config.MSG_ANN_UNAVAILABLE, ephemeral=True)
            return

        guild = interaction.guild
        buyer = interaction.user
        author_id = ann["author_id"]

        # --- validări ---
        if buyer.id == author_id:
            await interaction.followup.send(config.MSG_CANNOT_CONTACT_OWN, ephemeral=True)
            return
        if db.is_global_blocked(guild.id, buyer.id):
            await interaction.followup.send(config.MSG_GLOBAL_BLOCKED, ephemeral=True)
            return
        if db.is_blocked(guild.id, author_id, buyer.id):
            await interaction.followup.send(config.MSG_BLOCKED, ephemeral=True)
            return
        if db.has_active_ticket(guild.id, self.ann_id, buyer.id):
            await interaction.followup.send(config.MSG_ALREADY_TICKET, ephemeral=True)
            return

        # --- cooldown anti-spam (per utilizator) ---
        remaining = config.CONTACT_COOLDOWN_SECONDS - (time.time() - _contact_cd.get(buyer.id, 0))
        if remaining > 0:
            await interaction.followup.send(
                config.MSG_COOLDOWN.format(seconds=int(remaining) + 1), ephemeral=True)
            return

        # --- pregătim rolul de intermediar + categoria ---
        g = store.get_guild(guild.id)
        inter_role = guild.get_role(g["intermediary_role_id"]) if g.get("intermediary_role_id") else None
        category = guild.get_channel(g["ticket_category_id"]) if g.get("ticket_category_id") else None

        # --- permisiunile canalului de ticket ---
        # DOAR intermediarul + botul văd ticketul. Cumpărătorul ȘI autorul vorbesc
        # din DM (releu anonim) — niciunul nu e adăugat în canal.
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, manage_channels=True),
        }
        if inter_role:
            overwrites[inter_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True)

        # --- creăm canalul ---
        ch_name = config.TICKET_NAME.format(ann_id=self.ann_id, user=buyer.name)
        try:
            channel = await guild.create_text_channel(
                name=ch_name, overwrites=overwrites, category=category,
                reason=f"Ticket marketplace anunț #{self.ann_id}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Nu am permisiunea să creez canale (îmi trebuie «Manage Channels»).", ephemeral=True)
            return

        ticket_id = db.create_ticket(guild.id, self.ann_id, buyer.id, author_id, channel.id)
        _contact_cd[buyer.id] = time.time()   # pornim cooldown-ul după o creare reușită

        # --- mesaj de deschidere în ticket (doar intermediarul e pingat) ---
        ping = inter_role.mention if inter_role else ""
        await channel.send((ping + "\n" if ping else "") + config.TICKET_WELCOME.format(ann_id=self.ann_id))
        await channel.send(config.TICKET_CONTROLS_HINT, view=make_ticket_controls_view(ticket_id))

        # --- DM către autor ---
        stats = db.get_user_stats(guild.id, buyer.id)
        author = guild.get_member(author_id)
        if author is None:
            try:
                author = await interaction.client.fetch_user(author_id)
            except discord.NotFound:
                author = None

        dm_ok = False
        if author is not None:
            try:
                await author.send(
                    embed=build_dm_embed(buyer, self.ann_id, ticket_id, stats),
                    view=make_dm_view(ticket_id),
                )
                dm_ok = True
            except discord.Forbidden:
                dm_ok = False
        if not dm_ok:
            await channel.send(config.TICKET_AUTHOR_NO_DM)

        await log_action(guild, config.LOG_TICKET_OPEN,
                         {"Ticket": f"#{ticket_id}", "Anunț": f"#{self.ann_id}", "Cumpărător": buyer.mention})

        # --- DM de instrucțiuni către cumpărător (releu anonim) ---
        buyer_dm_ok = True
        try:
            await buyer.send(config.MSG_BUYER_RELAY_INFO.format(ann_id=self.ann_id))
        except discord.Forbidden:
            buyer_dm_ok = False

        # --- confirmare către cumpărător ---
        msg = config.MSG_TICKET_CREATED_ANON if buyer_dm_ok else config.MSG_BUYER_DM_CLOSED
        if inter_role is None:
            msg += "\n" + config.MSG_NO_INTERMEDIAR
        await interaction.followup.send(msg, ephemeral=True)


class EditButton(discord.ui.DynamicItem[discord.ui.Button],
                 template=config.CID_EDIT + r":(?P<ann_id>[0-9]+)"):
    def __init__(self, ann_id: int):
        self.ann_id = ann_id
        super().__init__(discord.ui.Button(
            label=config.BTN_EDIT, emoji=config.EMOJI_EDIT,
            style=discord.ButtonStyle.secondary,
            custom_id=f"{config.CID_EDIT}:{ann_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["ann_id"]))

    async def callback(self, interaction: discord.Interaction):
        ann = db.get_announcement(self.ann_id)
        if not ann or ann["status"] != "available":
            await interaction.response.send_message(config.MSG_ANN_UNAVAILABLE, ephemeral=True)
            return
        if interaction.user.id != ann["author_id"]:
            await interaction.response.send_message(config.MSG_NOT_AUTHOR, ephemeral=True)
            return
        await interaction.response.send_modal(EditAnnouncementModal(ann))


class BumpButton(discord.ui.DynamicItem[discord.ui.Button],
                 template=config.CID_BUMP + r":(?P<ann_id>[0-9]+)"):
    def __init__(self, ann_id: int):
        self.ann_id = ann_id
        super().__init__(discord.ui.Button(
            label=config.BTN_BUMP, emoji=config.EMOJI_BUMP,
            style=discord.ButtonStyle.secondary,
            custom_id=f"{config.CID_BUMP}:{ann_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["ann_id"]))

    async def callback(self, interaction: discord.Interaction):
        ann = db.get_announcement(self.ann_id)
        if not ann or ann["status"] != "available":
            await interaction.response.send_message(config.MSG_ANN_UNAVAILABLE, ephemeral=True)
            return
        if interaction.user.id != ann["author_id"]:
            await interaction.response.send_message(config.MSG_NOT_AUTHOR, ephemeral=True)
            return

        # cooldown 24h
        now = time.time()
        last = ann.get("last_bump_at") or 0
        remaining = int(config.BUMP_COOLDOWN_HOURS * 3600 - (now - last))
        if remaining > 0:
            h, m = remaining // 3600, (remaining % 3600) // 60
            t = f"{h}h {m}m" if h else f"{m}m"
            await interaction.response.send_message(
                config.MSG_BUMP_COOLDOWN.format(time=t), ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        ch = interaction.guild.get_channel(ann["channel_id"]) if ann.get("channel_id") else interaction.channel

        # șterge mesajul vechi
        if ann.get("message_id"):
            try:
                old = await ch.fetch_message(ann["message_id"])
                await old.delete()
            except discord.NotFound:
                pass

        # repostează (același ID, conținut neschimbat) ca cel mai recent
        msg = await ch.send(
            embed=build_announcement_embed(ann),
            view=make_announcement_view(self.ann_id),
        )
        db.bump_announcement(self.ann_id, msg.id, int(now))
        await log_action(interaction.guild, config.LOG_ANN_BUMPED,
                         {"Anunț": f"#{self.ann_id}", "Autor": interaction.user.mention})

        await interaction.followup.send(config.MSG_BUMP_DONE, ephemeral=True)


class WithdrawButton(discord.ui.DynamicItem[discord.ui.Button],
                     template=config.CID_WITHDRAW + r":(?P<ann_id>[0-9]+)"):
    def __init__(self, ann_id: int):
        self.ann_id = ann_id
        super().__init__(discord.ui.Button(
            label=config.BTN_WITHDRAW, emoji=config.EMOJI_WITHDRAW,
            style=discord.ButtonStyle.danger,
            custom_id=f"{config.CID_WITHDRAW}:{ann_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["ann_id"]))

    async def callback(self, interaction: discord.Interaction):
        ann = db.get_announcement(self.ann_id)
        if not ann or ann["status"] != "available":
            await interaction.response.send_message(config.MSG_ANN_UNAVAILABLE, ephemeral=True)
            return
        if interaction.user.id != ann["author_id"]:
            await interaction.response.send_message(config.MSG_NOT_AUTHOR, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # închide ticketele active pe acest anunț
        for t in db.get_active_tickets_for_announcement(self.ann_id):
            db.set_ticket_status(t["id"], "closed")
            tch = interaction.guild.get_channel(t["channel_id"]) if t.get("channel_id") else None
            if tch is not None:
                try:
                    await tch.send(config.MSG_ANN_WITHDRAWN_TICKET)
                except discord.HTTPException:
                    pass
                asyncio.create_task(_close_channel_later(tch, config.TICKET_CLOSE_DELAY))

        db.set_announcement_status(self.ann_id, "removed")
        await log_action(interaction.guild, config.LOG_ANN_WITHDRAWN,
                         {"Anunț": f"#{self.ann_id}", "Autor": interaction.user.mention})

        # șterge mesajul anunțului
        if ann.get("channel_id") and ann.get("message_id"):
            ch = interaction.guild.get_channel(ann["channel_id"])
            if ch is not None:
                try:
                    m = await ch.fetch_message(ann["message_id"])
                    await m.delete()
                except discord.NotFound:
                    pass

        await interaction.followup.send(config.MSG_ANN_WITHDRAWN, ephemeral=True)


def make_announcement_view(ann_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(ContactButton(ann_id))
    view.add_item(EditButton(ann_id))
    view.add_item(BumpButton(ann_id))
    view.add_item(WithdrawButton(ann_id))
    return view


# =========================================================
#  BUTOANELE DIN DM-ul AUTORULUI (persistente, cu ID-ul ticketului)
#  Logica reală (profil / acceptă / refuză / blochează) vine la pasul următor.
# =========================================================

class ProfileButton(discord.ui.DynamicItem[discord.ui.Button],
                    template=config.CID_TPROFILE + r":(?P<ticket_id>[0-9]+)"):
    def __init__(self, ticket_id: int):
        self.ticket_id = ticket_id
        super().__init__(discord.ui.Button(
            label=config.BTN_PROFILE, emoji=config.EMOJI_PROFILE,
            style=discord.ButtonStyle.secondary,
            custom_id=f"{config.CID_TPROFILE}:{ticket_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["ticket_id"]))

    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(config.MSG_TICKET_ALREADY_HANDLED)
            return
        guild = interaction.client.get_guild(ticket["guild_id"])
        buyer = guild.get_member(ticket["buyer_id"]) if guild else None
        if buyer is None:
            try:
                buyer = await interaction.client.fetch_user(ticket["buyer_id"])
            except discord.NotFound:
                await interaction.response.send_message("❌ Utilizatorul nu a putut fi găsit.")
                return
        stats = db.get_user_stats(ticket["guild_id"], ticket["buyer_id"])
        await interaction.response.send_message(embed=build_profile_embed(buyer, stats))


class AcceptButton(discord.ui.DynamicItem[discord.ui.Button],
                   template=config.CID_TACCEPT + r":(?P<ticket_id>[0-9]+)"):
    def __init__(self, ticket_id: int):
        self.ticket_id = ticket_id
        super().__init__(discord.ui.Button(
            label=config.BTN_ACCEPT, emoji=config.EMOJI_ACCEPT,
            style=discord.ButtonStyle.success,
            custom_id=f"{config.CID_TACCEPT}:{ticket_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["ticket_id"]))

    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_ticket(self.ticket_id)
        if not ticket or ticket["status"] != "open":
            await interaction.response.send_message(config.MSG_TICKET_ALREADY_HANDLED)
            return
        if interaction.user.id != ticket["author_id"]:
            await interaction.response.send_message(config.MSG_NOT_AUTHOR)
            return

        guild = interaction.client.get_guild(ticket["guild_id"])
        channel = guild.get_channel(ticket["channel_id"]) if guild else None
        if channel is None:
            db.set_ticket_status(self.ticket_id, "closed")
            await interaction.response.send_message(config.MSG_TICKET_ALREADY_HANDLED)
            return

        # Vânzătorul NU mai e adăugat în ticket — rămâne anonim și comunică prin DM (releu).
        await channel.send(config.MSG_ACCEPTED_TICKET)
        db.set_ticket_status(self.ticket_id, "accepted")
        await log_action(guild, config.LOG_ACCEPTED,
                         {"Ticket": f"#{self.ticket_id}", "Autor": interaction.user.mention},
                         color=config.COLOR_PRIMARY)

        await interaction.response.send_message(config.MSG_ACCEPTED_AUTHOR)
        try:
            await interaction.message.edit(view=None)  # dezactivează butoanele din DM
        except discord.HTTPException:
            pass


class RefuseButton(discord.ui.DynamicItem[discord.ui.Button],
                   template=config.CID_TREFUSE + r":(?P<ticket_id>[0-9]+)"):
    def __init__(self, ticket_id: int):
        self.ticket_id = ticket_id
        super().__init__(discord.ui.Button(
            label=config.BTN_REFUSE, emoji=config.EMOJI_REFUSE,
            style=discord.ButtonStyle.danger,
            custom_id=f"{config.CID_TREFUSE}:{ticket_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["ticket_id"]))

    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_ticket(self.ticket_id)
        if not ticket or ticket["status"] != "open":
            await interaction.response.send_message(config.MSG_TICKET_ALREADY_HANDLED)
            return
        if interaction.user.id != ticket["author_id"]:
            await interaction.response.send_message(config.MSG_NOT_AUTHOR)
            return

        db.set_ticket_status(self.ticket_id, "refused")
        guild = interaction.client.get_guild(ticket["guild_id"])
        channel = guild.get_channel(ticket["channel_id"]) if guild else None
        if channel is not None:
            try:
                await channel.send(config.MSG_REFUSED_BUYER + "\n" + config.MSG_TICKET_CLOSING)
            except discord.HTTPException:
                pass
            asyncio.create_task(_close_channel_later(channel, config.TICKET_CLOSE_DELAY))

        await log_action(guild, config.LOG_REFUSED,
                         {"Ticket": f"#{self.ticket_id}", "Autor": interaction.user.mention},
                         color=config.COLOR_DANGER)
        await interaction.response.send_message(config.MSG_REFUSED_AUTHOR)
        try:
            await interaction.message.edit(view=None)
        except discord.HTTPException:
            pass


class BlockButton(discord.ui.DynamicItem[discord.ui.Button],
                  template=config.CID_TBLOCK + r":(?P<ticket_id>[0-9]+)"):
    def __init__(self, ticket_id: int):
        self.ticket_id = ticket_id
        super().__init__(discord.ui.Button(
            label=config.BTN_BLOCK, emoji=config.EMOJI_BLOCK,
            style=discord.ButtonStyle.danger,
            custom_id=f"{config.CID_TBLOCK}:{ticket_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["ticket_id"]))

    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(config.MSG_TICKET_ALREADY_HANDLED)
            return
        if interaction.user.id != ticket["author_id"]:
            await interaction.response.send_message(config.MSG_NOT_AUTHOR)
            return
        await interaction.response.send_message(
            config.MSG_BLOCK_CONFIRM, view=ConfirmBlockView(self.ticket_id))


class ConfirmBlockView(discord.ui.View):
    """Confirmarea pentru blocare (tranzitorie, 60s). Doar autorul poate confirma."""
    def __init__(self, ticket_id: int):
        super().__init__(timeout=60)
        self.ticket_id = ticket_id

    @discord.ui.button(label=config.BTN_CONFIRM, emoji=config.EMOJI_BLOCK, style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.edit_message(content=config.MSG_TICKET_ALREADY_HANDLED, view=None)
            return
        if interaction.user.id != ticket["author_id"]:
            await interaction.response.send_message(config.MSG_NOT_AUTHOR)
            return

        db.add_block(ticket["guild_id"], ticket["author_id"], ticket["buyer_id"])
        db.set_ticket_status(self.ticket_id, "closed")

        guild = interaction.client.get_guild(ticket["guild_id"])
        channel = guild.get_channel(ticket["channel_id"]) if guild else None
        if channel is not None:
            try:
                await channel.send(config.MSG_REFUSED_BUYER)
            except discord.HTTPException:
                pass
            asyncio.create_task(_close_channel_later(channel, config.TICKET_CLOSE_DELAY))

        await log_action(guild, config.LOG_BLOCKED,
                         {"Autor": f"<@{ticket['author_id']}>", "Blocat": f"<@{ticket['buyer_id']}>"},
                         color=config.COLOR_DANGER)
        await interaction.response.edit_message(content=config.MSG_BLOCKED_DONE, view=None)

    @discord.ui.button(label=config.BTN_CANCEL, style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content=config.MSG_BLOCK_CANCELLED, view=None)


def make_dm_view(ticket_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(AcceptButton(ticket_id))
    view.add_item(RefuseButton(ticket_id))
    view.add_item(BlockButton(ticket_id))
    return view


# =========================================================
#  BUTONUL DE FINALIZARE (în ticket, doar intermediarul îl poate apăsa)
# =========================================================

class FinalizeButton(discord.ui.DynamicItem[discord.ui.Button],
                     template=config.CID_FINALIZE + r":(?P<ticket_id>[0-9]+)"):
    def __init__(self, ticket_id: int):
        self.ticket_id = ticket_id
        super().__init__(discord.ui.Button(
            label=config.BTN_FINALIZE, emoji=config.EMOJI_FINALIZE,
            style=discord.ButtonStyle.success,
            custom_id=f"{config.CID_FINALIZE}:{ticket_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["ticket_id"]))

    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_ticket(self.ticket_id)
        if not ticket or ticket["status"] in ("finalized", "refused", "closed"):
            await interaction.response.send_message(config.MSG_TICKET_CLOSED, ephemeral=True)
            return

        guild = interaction.guild
        member = interaction.user
        role_id = store.get_guild(guild.id).get("intermediary_role_id")
        allowed = (role_id and any(r.id == role_id for r in member.roles)) \
            or member.guild_permissions.administrator
        if not allowed:
            await interaction.response.send_message(config.MSG_ONLY_INTERMEDIAR, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        ann_id = ticket["announcement_id"]
        ann = db.get_announcement(ann_id)

        # 1) anunțul devine finalizat
        db.set_announcement_status(ann_id, "finalized")

        # 2) ștergem mesajul anunțului
        if ann and ann.get("channel_id") and ann.get("message_id"):
            ach = guild.get_channel(ann["channel_id"])
            if ach is not None:
                try:
                    m = await ach.fetch_message(ann["message_id"])
                    await m.delete()
                except discord.NotFound:
                    pass

        # 3) +1 „schimb finalizat" pentru cumpărător și autor
        db.increment_user_stat(guild.id, ticket["buyer_id"], "completed")
        db.increment_user_stat(guild.id, ticket["author_id"], "completed")
        db.increment_user_stat(guild.id, ticket["author_id"], "announcements_finished")

        # 4) închidem celelalte tickete active pe acest anunț
        for other in db.get_active_tickets_for_announcement(ann_id, exclude_ticket_id=self.ticket_id):
            db.set_ticket_status(other["id"], "closed")
            och = guild.get_channel(other["channel_id"]) if other.get("channel_id") else None
            if och is not None:
                try:
                    await och.send(config.MSG_FINALIZE_OTHERS)
                except discord.HTTPException:
                    pass
                asyncio.create_task(_close_channel_later(och, config.TICKET_CLOSE_DELAY))
            await log_action(guild, config.LOG_TICKET_CLOSED,
                             {"Ticket": f"#{other['id']}", "Motiv": "schimb finalizat"})

        # 5) închidem ticketul curent (îl ștergem, nu îl arhivăm)
        db.set_ticket_status(self.ticket_id, "finalized")
        channel = interaction.channel
        await log_action(guild, config.LOG_FINALIZED,
                         {"Anunț": f"#{ann_id}", "Ticket": f"#{self.ticket_id}", "Intermediar": member.mention},
                         color=config.COLOR_PRIMARY, success=True)
        try:
            await channel.send(config.MSG_FINALIZE_DONE + "\n" + config.MSG_TICKET_CLOSING)
        except discord.HTTPException:
            pass
        asyncio.create_task(_close_channel_later(channel, config.TICKET_CLOSE_DELAY))

        # 6) anunțăm ambele părți în DM + curățăm mesajele releu din DM-urile lor
        asyncio.create_task(_finalize_notify_and_clean(interaction.client, ticket["buyer_id"], ann_id))
        asyncio.create_task(_finalize_notify_and_clean(interaction.client, ticket["author_id"], ann_id))

        await interaction.followup.send("✅ Gata.", ephemeral=True)


async def _finalize_notify_and_clean(client, user_id, ann_id):
    """La finalizare: șterge mesajele releu trimise de bot în DM-ul userului,
    apoi îi trimite anunțul de finalizare (care rămâne)."""
    if not user_id:
        return
    user = client.get_user(user_id)
    if user is None:
        try:
            user = await client.fetch_user(user_id)
        except discord.NotFound:
            return
    # curăță mesajele pe care botul le-a trimis în acest DM (nu poate șterge ce a scris userul)
    try:
        dm = user.dm_channel or await user.create_dm()
        old = [m async for m in dm.history(limit=100) if m.author.id == client.user.id]
        for m in old:
            try:
                await m.delete()
            except discord.HTTPException:
                pass
    except discord.HTTPException:
        pass
    # anunțul de finalizare (rămâne)
    try:
        await user.send(config.MSG_FINALIZE_DM.format(ann_id=ann_id))
    except discord.HTTPException:
        pass


def make_finalize_view(ticket_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(FinalizeButton(ticket_id))
    return view


# =========================================================
#  RAPORTĂRI (confirmate de staff)
# =========================================================

def _is_staff(guild, member) -> bool:
    role_id = store.get_guild(guild.id).get("intermediary_role_id")
    has_role = role_id and any(r.id == role_id for r in getattr(member, "roles", []))
    return bool(has_role) or member.guild_permissions.administrator


def build_report_embed(report_id, reporter_id, reported_id, reason) -> discord.Embed:
    e = discord.Embed(title=f"{config.REPORT_TITLE} #{report_id}",
                      color=config.COLOR_WARNING, timestamp=discord.utils.utcnow())
    e.add_field(name=config.REPORT_F_REPORTER, value=f"<@{reporter_id}>", inline=True)
    e.add_field(name=config.REPORT_F_REPORTED, value=f"<@{reported_id}>", inline=True)
    e.add_field(name=config.REPORT_F_REASON, value=reason or "—", inline=False)
    return e


class ReportModal(discord.ui.Modal):
    def __init__(self, ticket_id: int, reported_id: int):
        super().__init__(title=config.REPORT_MODAL_TITLE)
        self.ticket_id = ticket_id
        self.reported_id = reported_id
        self.reason = discord.ui.TextInput(
            label="Motiv", style=discord.TextStyle.paragraph, required=True, max_length=500)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        reason = self.reason.value.strip()
        report_id = db.create_report(guild.id, self.ticket_id, interaction.user.id, self.reported_id, reason)
        # raportul rămâne PRIVAT — îl trimitem în ticket (unde e intermediarul), nu în logul public
        role_id = store.get_guild(guild.id).get("intermediary_role_id")
        content = f"<@&{role_id}>" if role_id else None
        await interaction.channel.send(
            content=content,
            embed=build_report_embed(report_id, interaction.user.id, self.reported_id, reason),
            view=make_report_review_view(report_id),
            allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
        )
        await interaction.response.send_message(config.MSG_REPORT_SENT, ephemeral=True)


class ReportButton(discord.ui.DynamicItem[discord.ui.Button],
                   template=config.CID_REPORT + r":(?P<ticket_id>[0-9]+)"):
    def __init__(self, ticket_id: int):
        self.ticket_id = ticket_id
        super().__init__(discord.ui.Button(
            label=config.BTN_REPORT, emoji=config.EMOJI_REPORT,
            style=discord.ButtonStyle.secondary,
            custom_id=f"{config.CID_REPORT}:{ticket_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["ticket_id"]))

    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_ticket(self.ticket_id)
        if not ticket:
            await interaction.response.send_message(config.MSG_TICKET_CLOSED, ephemeral=True)
            return
        uid = interaction.user.id
        if uid == ticket["buyer_id"]:
            reported_id = ticket["author_id"]
        elif uid == ticket["author_id"]:
            reported_id = ticket["buyer_id"]
        else:
            await interaction.response.send_message(config.MSG_REPORT_ONLY_PARTIES, ephemeral=True)
            return
        await interaction.response.send_modal(ReportModal(self.ticket_id, reported_id))


class ConfirmReportButton(discord.ui.DynamicItem[discord.ui.Button],
                          template=config.CID_REPORT_OK + r":(?P<report_id>[0-9]+)"):
    def __init__(self, report_id: int):
        self.report_id = report_id
        super().__init__(discord.ui.Button(
            label=config.BTN_REPORT_CONFIRM, emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id=f"{config.CID_REPORT_OK}:{report_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["report_id"]))

    async def callback(self, interaction: discord.Interaction):
        report = db.get_report(self.report_id)
        if not report or report["status"] != "pending":
            await interaction.response.send_message(config.MSG_REPORT_HANDLED, ephemeral=True)
            return
        if not _is_staff(interaction.guild, interaction.user):
            await interaction.response.send_message(config.MSG_ONLY_STAFF, ephemeral=True)
            return
        db.set_report_status(self.report_id, "confirmed")
        db.increment_user_stat(report["guild_id"], report["reported_id"], "confirmed_reports")
        await log_action(interaction.guild, config.LOG_REPORT,
                         {"Raport": f"#{self.report_id}", "Reclamat": f"<@{report['reported_id']}>",
                          "Staff": interaction.user.mention}, color=config.COLOR_DANGER)
        await interaction.response.edit_message(content=config.MSG_REPORT_CONFIRMED, view=None)


class RejectReportButton(discord.ui.DynamicItem[discord.ui.Button],
                         template=config.CID_REPORT_NO + r":(?P<report_id>[0-9]+)"):
    def __init__(self, report_id: int):
        self.report_id = report_id
        super().__init__(discord.ui.Button(
            label=config.BTN_REPORT_REJECT, emoji="❌",
            style=discord.ButtonStyle.danger,
            custom_id=f"{config.CID_REPORT_NO}:{report_id}",
        ))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["report_id"]))

    async def callback(self, interaction: discord.Interaction):
        report = db.get_report(self.report_id)
        if not report or report["status"] != "pending":
            await interaction.response.send_message(config.MSG_REPORT_HANDLED, ephemeral=True)
            return
        if not _is_staff(interaction.guild, interaction.user):
            await interaction.response.send_message(config.MSG_ONLY_STAFF, ephemeral=True)
            return
        db.set_report_status(self.report_id, "rejected")
        await interaction.response.edit_message(content=config.MSG_REPORT_REJECTED, view=None)


def make_report_review_view(report_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(ConfirmReportButton(report_id))
    view.add_item(RejectReportButton(report_id))
    return view


def make_ticket_controls_view(ticket_id: int) -> discord.ui.View:
    """Butoanele din ticket: finalizare (staff) + raportare (părți)."""
    view = discord.ui.View(timeout=None)
    view.add_item(FinalizeButton(ticket_id))
    view.add_item(ReportButton(ticket_id))
    return view


# =========================================================
#  MODALUL DE CREARE ANUNȚ (funcția 2)
# =========================================================

class CreateAnnouncementModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title=config.MODAL_TITLE)
        self.server_from = discord.ui.TextInput(
            label="Server din care vinzi", required=False, max_length=100, placeholder="(Opțional)")
        self.server_to = discord.ui.TextInput(
            label="Server pe care cauți", required=False, max_length=100, placeholder="(Opțional)")
        self.offer = discord.ui.TextInput(
            label="Ce oferi", style=discord.TextStyle.paragraph, required=False, max_length=500,
            placeholder="(Opțional)")
        self.want = discord.ui.TextInput(
            label="Ce dorești", style=discord.TextStyle.paragraph, required=False, max_length=500,
            placeholder="(Opțional)")
        for item in (self.server_from, self.server_to, self.offer, self.want):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        offer = self.offer.value.strip()
        want = self.want.value.strip()
        if not offer and not want:
            await interaction.response.send_message(
                "❌ Completează măcar «Ce oferi» sau «Ce dorești».", ephemeral=True)
            return

        ann_id = db.create_announcement(
            interaction.guild_id, interaction.user.id,
            server_from=self.server_from.value.strip() or None,
            server_to=self.server_to.value.strip() or None,
            offer=offer or None,
            want=want or None,
            ratio=None,
            details=None,
        )
        ann = db.get_announcement(ann_id)
        db.increment_user_stat(interaction.guild_id, interaction.user.id, "announcements_created")

        g = store.get_guild(interaction.guild_id)
        channel = interaction.guild.get_channel(g.get("channel_id")) or interaction.channel
        msg = await channel.send(
            embed=build_announcement_embed(ann),
            view=make_announcement_view(ann_id),
        )
        db.set_announcement_message(ann_id, channel.id, msg.id)
        await log_action(interaction.guild, config.LOG_ANN_CREATED,
                         {"Anunț": f"#{ann_id}", "Autor": interaction.user.mention},
                         color=config.COLOR_PRIMARY)

        await interaction.response.send_message(
            f"✅ Anunțul tău **#{ann_id}** a fost publicat în {channel.mention}.", ephemeral=True)


class EditAnnouncementModal(discord.ui.Modal):
    """Formular de editare, precompletat cu valorile curente ale anunțului."""
    def __init__(self, ann: dict):
        super().__init__(title=config.EDIT_MODAL_TITLE)
        self.ann_id = ann["id"]
        self.server_from = discord.ui.TextInput(
            label="Server din care vinzi", required=False, max_length=100,
            default=ann.get("server_from") or "", placeholder="(Opțional)")
        self.server_to = discord.ui.TextInput(
            label="Server pe care cauți", required=False, max_length=100,
            default=ann.get("server_to") or "", placeholder="(Opțional)")
        self.offer = discord.ui.TextInput(
            label="Ce oferi", style=discord.TextStyle.paragraph, required=False, max_length=500,
            default=ann.get("offer") or "", placeholder="(Opțional)")
        self.want = discord.ui.TextInput(
            label="Ce dorești", style=discord.TextStyle.paragraph, required=False, max_length=500,
            default=ann.get("want") or "", placeholder="(Opțional)")
        for item in (self.server_from, self.server_to, self.offer, self.want):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        offer = self.offer.value.strip()
        want = self.want.value.strip()
        if not offer and not want:
            await interaction.response.send_message(
                "❌ Completează măcar «Ce oferi» sau «Ce dorești».", ephemeral=True)
            return

        db.update_announcement(
            self.ann_id,
            server_from=self.server_from.value.strip() or None,
            server_to=self.server_to.value.strip() or None,
            offer=offer or None,
            want=want or None,
            ratio=None,
        )
        ann = db.get_announcement(self.ann_id)

        # actualizăm embed-ul mesajului existent
        ch = interaction.guild.get_channel(ann["channel_id"]) if ann.get("channel_id") else None
        if ch is not None and ann.get("message_id"):
            try:
                msg = await ch.fetch_message(ann["message_id"])
                await msg.edit(embed=build_announcement_embed(ann))
            except discord.NotFound:
                pass

        await log_action(interaction.guild, config.LOG_ANN_EDITED,
                         {"Anunț": f"#{self.ann_id}", "Autor": interaction.user.mention})
        await interaction.response.send_message(config.MSG_ANN_UPDATED, ephemeral=True)


# =========================================================
#  PANOUL PERMANENT
# =========================================================

class CreatePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label=config.PANEL_BUTTON_LABEL, emoji=config.EMOJI_CREATE,
        style=discord.ButtonStyle.success, custom_id=config.CID_CREATE,
    )
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        if db.is_global_blocked(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(config.MSG_GLOBAL_BLOCKED, ephemeral=True)
            return
        await interaction.response.send_modal(CreateAnnouncementModal())


# =========================================================
#  COG + COMENZI ADMIN
# =========================================================

class Marketplace(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(CreatePanelView())
        # butoanele de pe anunțuri
        self.bot.add_dynamic_items(ContactButton, EditButton, BumpButton, WithdrawButton)
        # butoanele din DM-ul autorului
        self.bot.add_dynamic_items(ProfileButton, AcceptButton, RefuseButton, BlockButton)
        # butonul de finalizare din ticket
        self.bot.add_dynamic_items(FinalizeButton)
        # raportări (buton în ticket + confirmare/respingere staff)
        self.bot.add_dynamic_items(ReportButton, ConfirmReportButton, RejectReportButton)

    group = app_commands.Group(
        name="marketplace",
        description="Administrare marketplace",
        default_permissions=discord.Permissions(administrator=True),
    )

    async def _post_panel(self, channel: discord.TextChannel) -> discord.Message:
        return await channel.send(embed=build_panel_embed(), view=CreatePanelView())

    @group.command(name="setup", description="Setează canalul de marketplace (opțional: rol intermediar, categorie, loguri)")
    @app_commands.describe(
        canal="Canalul în care va sta panoul de marketplace",
        rol_intermediar="Rolul care intră automat în fiecare ticket (opțional)",
        categorie="Categoria în care se creează canalele de ticket (opțional)",
        canal_loguri="Canalul privat în care se scriu logurile (opțional)",
    )
    async def setup_cmd(self, interaction: discord.Interaction,
                        canal: discord.TextChannel,
                        rol_intermediar: discord.Role = None,
                        categorie: discord.CategoryChannel = None,
                        canal_loguri: discord.TextChannel = None):
        msg = await self._post_panel(canal)
        store.set_guild_value(interaction.guild_id, "channel_id", canal.id)
        store.set_guild_value(interaction.guild_id, "panel_message_id", msg.id)
        if rol_intermediar:
            store.set_guild_value(interaction.guild_id, "intermediary_role_id", rol_intermediar.id)
        if categorie:
            store.set_guild_value(interaction.guild_id, "ticket_category_id", categorie.id)
        if canal_loguri:
            store.set_guild_value(interaction.guild_id, "log_channel_id", canal_loguri.id)

        parts = [f"✅ Marketplace setat în {canal.mention}."]
        if rol_intermediar:
            parts.append(f"Intermediar: {rol_intermediar.mention}")
        if categorie:
            parts.append(f"Categorie tickete: **{categorie.name}**")
        if canal_loguri:
            parts.append(f"Loguri: {canal_loguri.mention}")
        await interaction.response.send_message("\n".join(parts), ephemeral=True)

    @group.command(name="panel", description="Regenerează mesajul permanent al panoului")
    async def panel_cmd(self, interaction: discord.Interaction):
        g = store.get_guild(interaction.guild_id)
        channel_id = g.get("channel_id")
        if not channel_id:
            await interaction.response.send_message(
                "❌ Nu ai setat încă un canal. Folosește întâi `/marketplace setup`.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            await interaction.response.send_message(
                "❌ Canalul salvat nu mai există. Rulează din nou `/marketplace setup`.", ephemeral=True)
            return
        old_id = g.get("panel_message_id")
        if old_id:
            try:
                old = await channel.fetch_message(old_id)
                await old.delete()
            except discord.NotFound:
                pass
        msg = await self._post_panel(channel)
        store.set_guild_value(interaction.guild_id, "panel_message_id", msg.id)
        await interaction.response.send_message("✅ Panou regenerat.", ephemeral=True)

    @group.command(name="delete", description="Șterge un anunț după ID")
    @app_commands.describe(anunt="ID-ul anunțului")
    async def delete_cmd(self, interaction: discord.Interaction, anunt: int):
        ann = db.get_announcement(anunt)
        if not ann or ann["guild_id"] != interaction.guild_id:
            await interaction.response.send_message("❌ Anunț inexistent.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)

        # șterge mesajul anunțului
        if ann.get("channel_id") and ann.get("message_id"):
            ch = interaction.guild.get_channel(ann["channel_id"])
            if ch is not None:
                try:
                    m = await ch.fetch_message(ann["message_id"])
                    await m.delete()
                except discord.NotFound:
                    pass
        db.set_announcement_status(anunt, "removed")

        # închide ticketele active pe acest anunț
        for t in db.get_active_tickets_for_announcement(anunt):
            db.set_ticket_status(t["id"], "closed")
            tch = interaction.guild.get_channel(t["channel_id"]) if t.get("channel_id") else None
            if tch is not None:
                try:
                    await tch.send(config.MSG_ANN_REMOVED_TICKET)
                except discord.HTTPException:
                    pass
                asyncio.create_task(_close_channel_later(tch, config.TICKET_CLOSE_DELAY))

        await log_action(interaction.guild, config.LOG_ANN_DELETED,
                         {"Anunț": f"#{anunt}", "Admin": interaction.user.mention},
                         color=config.COLOR_DANGER)
        await interaction.followup.send(f"✅ Anunțul #{anunt} a fost șters.", ephemeral=True)

    @group.command(name="stats", description="Statistici marketplace (sau ale unui utilizator)")
    @app_commands.describe(utilizator="Vezi statisticile unui anumit utilizator (opțional)")
    async def stats_cmd(self, interaction: discord.Interaction, utilizator: discord.User = None):
        if utilizator is not None:
            s = db.get_user_stats(interaction.guild_id, utilizator.id)
            e = discord.Embed(title=f"📊 Statistici — {utilizator.name}", color=config.COLOR_INFO)
            e.add_field(name=config.PROFILE_F_COMPLETED, value=str(s["completed"]))
            e.add_field(name=config.PROFILE_F_CANCELLED, value=str(s["cancelled"]))
            e.add_field(name=config.PROFILE_F_REPORTS, value=str(s["confirmed_reports"]))
            e.add_field(name="📢 Anunțuri create", value=str(s["announcements_created"]))
            e.add_field(name="✅ Anunțuri finalizate", value=str(s["announcements_finished"]))
            await interaction.response.send_message(embed=e, ephemeral=True)
            return

        st = db.get_marketplace_stats(interaction.guild_id)
        e = discord.Embed(title="📊 Statistici marketplace", color=config.COLOR_INFO)
        e.add_field(name="Anunțuri (total)", value=str(st["ann_total"]))
        e.add_field(name="Disponibile", value=str(st["ann_available"]))
        e.add_field(name="Finalizate", value=str(st["ann_finished"]))
        e.add_field(name="Tickete (total)", value=str(st["tickets_total"]))
        e.add_field(name="Tickete active", value=str(st["tickets_open"]))
        e.add_field(name="Blocări (autor→user)", value=str(st["blocks"]))
        e.add_field(name="Blacklist", value=str(st["blacklisted"]))
        await interaction.response.send_message(embed=e, ephemeral=True)

    @group.command(name="logs", description="Setează sau arată canalul de loguri")
    @app_commands.describe(canal="Canalul de loguri (lasă gol ca să vezi cel curent)")
    async def logs_cmd(self, interaction: discord.Interaction, canal: discord.TextChannel = None):
        if canal is not None:
            store.set_guild_value(interaction.guild_id, "log_channel_id", canal.id)
            await interaction.response.send_message(f"✅ Loguri setate în {canal.mention}.", ephemeral=True)
            return
        log_id = store.get_guild(interaction.guild_id).get("log_channel_id")
        if log_id:
            await interaction.response.send_message(f"Canal loguri curent: <#{log_id}>", ephemeral=True)
        else:
            await interaction.response.send_message("Niciun canal de loguri setat.", ephemeral=True)

    @group.command(name="blacklist", description="Restricționează un utilizator de la marketplace")
    @app_commands.describe(utilizator="Utilizatorul de restricționat", motiv="Motiv (opțional)")
    async def blacklist_cmd(self, interaction: discord.Interaction,
                            utilizator: discord.User, motiv: str = None):
        db.add_global_block(interaction.guild_id, utilizator.id, motiv)
        await log_action(interaction.guild, config.LOG_BLACKLIST,
                         {"Utilizator": utilizator.mention, "Admin": interaction.user.mention,
                          "Motiv": motiv or "—"}, color=config.COLOR_DANGER)
        await interaction.response.send_message(
            f"✅ {utilizator.mention} a fost adăugat pe blacklist.", ephemeral=True)

    @group.command(name="unblock", description="Scoate un utilizator de pe blacklist")
    @app_commands.describe(utilizator="Utilizatorul de scos de pe blacklist")
    async def unblock_cmd(self, interaction: discord.Interaction, utilizator: discord.User):
        db.remove_global_block(interaction.guild_id, utilizator.id)
        await interaction.response.send_message(
            f"✅ {utilizator.mention} a fost scos de pe blacklist.", ephemeral=True)

    @group.command(name="reload", description="Reîncarcă modulul marketplace (fără restart complet)")
    async def reload_cmd(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension("cogs.marketplace")
            await interaction.followup.send("✅ Modul reîncărcat.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Reîncărcare eșuată: {e}", ephemeral=True)

    # =========================================================
    #  RELEU ANONIM (cameră): cumpărător ↔ vânzător ↔ intermediar
    #  Cumpărătorul și vânzătorul vorbesc din DM; doar intermediarul e în ticket.
    #  Cumpărătorul și vânzătorul rămân anonimi unul față de celălalt.
    # =========================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            await self._relay_from_dm(message)
        elif message.channel.name.startswith("ticket-"):
            await self._relay_from_ticket(message)

    def _find_relay_ticket(self, user_id):
        """Cel mai recent ticket activ în care userul e cumpărător sau vânzător."""
        candidates = [(t, "seller") for t in db.get_accepted_tickets_for_seller(user_id)]
        candidates += [(t, "buyer") for t in db.get_active_tickets_for_buyer(user_id)]
        if not candidates:
            return None, None
        candidates.sort(key=lambda tr: tr[0]["id"], reverse=True)
        return candidates[0]

    async def _dm_user(self, user_id, content):
        if not user_id:
            return
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.NotFound:
                return
        try:
            await user.send(content)
        except discord.HTTPException:
            pass

    async def _relay_from_dm(self, message: discord.Message):
        ticket, role = self._find_relay_ticket(message.author.id)
        if not ticket:
            return
        body = _relay_body(message)
        if not body:
            return
        guild = self.bot.get_guild(ticket["guild_id"])
        channel = guild.get_channel(ticket["channel_id"]) if guild else None

        if role == "buyer":
            label = config.RELAY_BUYER_NAME
            # către vânzător doar dacă a acceptat (e în discuție)
            if ticket["status"] == "accepted":
                await self._dm_user(ticket["author_id"], f"**{label}:** {body}")
        else:  # seller
            label = config.RELAY_SELLER_NAME
            await self._dm_user(ticket["buyer_id"], f"**{label}:** {body}")

        # în ticket (îl vede intermediarul)
        if channel is not None:
            embed = discord.Embed(description=body, color=config.COLOR_INFO)
            embed.set_author(name=label)
            await channel.send(embed=embed)

    async def _relay_from_ticket(self, message: discord.Message):
        """Mesaj scris de intermediar în ticket → la ambele părți în DM."""
        ticket = db.get_ticket_by_channel(message.channel.id)
        if not ticket or ticket["status"] not in ("open", "accepted"):
            return
        body = _relay_body(message)
        if not body:
            return
        text = f"**{config.RELAY_STAFF_NAME}:** {body}"
        await self._dm_user(ticket["buyer_id"], text)
        if ticket["status"] == "accepted":
            await self._dm_user(ticket["author_id"], text)


async def setup(bot: commands.Bot):
    await bot.add_cog(Marketplace(bot))
