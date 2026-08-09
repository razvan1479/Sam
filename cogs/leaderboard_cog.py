# cogs/leaderboard_cog.py — leaderboard de promoteri.
# Un mesaj per promoter (rang + nume + ❤️/💔 + butoanele [📂][👍][👎]), sortat după scor.
# La fiecare vot: recalculează, re-sortează și editează toate mesajele.

import asyncio
import time

import discord
from discord import app_commands
from discord.ext import commands

import db
import store

CID_ACCESS = "lb:access"
CID_LIKE = "lb:like"
CID_DISLIKE = "lb:dislike"

VOTE_COOLDOWN = 30      # secunde între voturi
ACCESS_SECONDS = 300    # 5 minute acces temporar

CID_SELECT = "lb:sel"
TIER_SIZE = 10
# (nume, emoji, culoare) — locurile 1-10 VIP, 11-20 Gold, 21-30 Silver, 31-40 Bronze, 41+ Iron
TIER_DEFS = [
    ("VIP", "👑", 0xF1C40F),
    ("Gold", "🥇", 0xE5B80B),
    ("Silver", "🥈", 0xBFC1C6),
    ("Bronze", "🥉", 0xCD7F32),
    ("Iron", "⚙️", 0x71797E),
]

_vote_cd: dict[int, float] = {}   # user_id -> ultimul vot (în memorie)


def render_row(rank: int, name: str, likes: int, dislikes: int) -> str:
    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
    return f"{medal}  **{name}**   ❤️ {likes} | 💔 {dislikes}"


async def _revoke_later(channel: discord.TextChannel, member: discord.Member, secs: int):
    await asyncio.sleep(secs)
    try:
        await channel.set_permissions(member, overwrite=None, reason="acces temporar expirat")
    except discord.HTTPException:
        pass


# =========================================================
#  Butoanele de pe fiecare promoter (persistente)
# =========================================================

class AccessButton(discord.ui.DynamicItem[discord.ui.Button],
                   template=CID_ACCESS + r":(?P<pid>[0-9]+)"):
    def __init__(self, pid: int):
        self.pid = pid
        super().__init__(discord.ui.Button(emoji="📂", style=discord.ButtonStyle.secondary,
                                            custom_id=f"{CID_ACCESS}:{pid}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["pid"]))

    async def callback(self, interaction: discord.Interaction):
        promoter = db.get_promoter(self.pid)
        if not promoter:
            await interaction.response.send_message("❌ Promoter inexistent.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(promoter["channel_id"]) if promoter.get("channel_id") else None
        if channel is None:
            await interaction.response.send_message("❌ Canalul promoterului nu există.", ephemeral=True)
            return
        try:
            await channel.set_permissions(
                interaction.user, view_channel=True, send_messages=False,
                read_message_history=True, reason="acces temporar leaderboard")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Nu am permisiunea să dau acces la canal.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"📂 Ai acces **5 minute** la {channel.mention} (doar citire).", ephemeral=True)
        asyncio.create_task(_revoke_later(channel, interaction.user, ACCESS_SECONDS))


async def _do_vote(interaction: discord.Interaction, pid: int, value: int, deja_msg: str):
    promoter = db.get_promoter(pid)
    if not promoter:
        await interaction.response.send_message("❌ Promoter inexistent.", ephemeral=True)
        return
    if interaction.user.id == promoter["user_id"]:
        await interaction.response.send_message("❌ Nu îți poți vota propriul profil.", ephemeral=True)
        return
    current = db.get_vote(pid, interaction.user.id)
    if current == value:
        await interaction.response.send_message(deja_msg, ephemeral=True)
        return
    now = time.time()
    remaining = VOTE_COOLDOWN - (now - _vote_cd.get(interaction.user.id, 0))
    if remaining > 0:
        await interaction.response.send_message(
            f"⏳ Prea repede — mai așteaptă {int(remaining) + 1}s.", ephemeral=True)
        return
    db.set_vote(pid, interaction.user.id, value)
    _vote_cd[interaction.user.id] = now
    cog = interaction.client.get_cog("Leaderboard")
    if cog:
        await cog.refresh_leaderboard(interaction.guild)
    await interaction.response.send_message(
        "👍 Like înregistrat." if value == 1 else "👎 Dislike înregistrat.", ephemeral=True)


class LikeButton(discord.ui.DynamicItem[discord.ui.Button],
                 template=CID_LIKE + r":(?P<pid>[0-9]+)"):
    def __init__(self, pid: int):
        self.pid = pid
        super().__init__(discord.ui.Button(emoji="👍", style=discord.ButtonStyle.success,
                                            custom_id=f"{CID_LIKE}:{pid}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["pid"]))

    async def callback(self, interaction: discord.Interaction):
        await _do_vote(interaction, self.pid, 1, "ℹ️ Ai votat deja cu 👍.")


class DislikeButton(discord.ui.DynamicItem[discord.ui.Button],
                    template=CID_DISLIKE + r":(?P<pid>[0-9]+)"):
    def __init__(self, pid: int):
        self.pid = pid
        super().__init__(discord.ui.Button(emoji="👎", style=discord.ButtonStyle.danger,
                                            custom_id=f"{CID_DISLIKE}:{pid}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["pid"]))

    async def callback(self, interaction: discord.Interaction):
        await _do_vote(interaction, self.pid, -1, "ℹ️ Ai votat deja cu 👎.")


def make_promoter_view(pid: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(AccessButton(pid))
    view.add_item(LikeButton(pid))
    view.add_item(DislikeButton(pid))
    return view


# =========================================================
#  Tiere (VIP / Gold / Silver / Bronze / Iron) — un embed per tieră
# =========================================================

def _display_name(guild, p):
    m = guild.get_member(p["user_id"])
    return m.display_name if m else p["name"]


def build_tiers(promoters):
    """Împarte promoterii (deja sortați desc după scor) în tiere de câte 10.
    Ultima tieră (Iron) ia tot restul. Returnează doar tierele care au promoteri."""
    tiers = []
    n = len(TIER_DEFS)
    for i, (name, emoji, color) in enumerate(TIER_DEFS):
        start = i * TIER_SIZE
        chunk = promoters[start:] if i == n - 1 else promoters[start:start + TIER_SIZE]
        if chunk:
            tiers.append((name, emoji, color, chunk, start))
    return tiers


def build_tier_embed(guild, name, emoji, color, chunk, start):
    # tot clasamentul într-un SINGUR bloc monospace → coloane aliniate perfect
    entries = []
    for j, p in enumerate(chunk):
        entries.append((start + j + 1, _display_name(guild, p), p["likes"], p["dislikes"]))
    name_w = min(max((len(e[1]) for e in entries), default=4), 16)
    like_w = max((len(str(e[2])) for e in entries), default=1)
    dis_w = max((len(str(e[3])) for e in entries), default=1)
    lines = []
    for rank, nm, l, d in entries:
        nm2 = (nm[:name_w - 1] + "…") if len(nm) > name_w else nm.ljust(name_w)
        rank_col = f"{str(rank) + '.':<4}"
        lines.append(f"{rank_col}{nm2}   ❤️ {str(l).rjust(like_w)}   💔 {str(d).rjust(dis_w)}")
    desc = "```\n" + "\n".join(lines) + "\n```"
    return discord.Embed(title=f"{emoji}  {name}", description=desc, color=discord.Color(color))


def build_tier_view(guild, chunk, start):
    options = []
    for j, p in enumerate(chunk[:25]):
        rank = start + j + 1
        options.append(discord.SelectOption(
            label=f"{rank}. {_display_name(guild, p)}"[:100], value=str(p["id"])))
    return LeaderboardView(options)


class TierSelect(discord.ui.Select):
    def __init__(self, options=None):
        super().__init__(custom_id=CID_SELECT, placeholder="Alege un promoter…",
                         min_values=1, max_values=1,
                         options=options or [discord.SelectOption(label="—", value="0")])

    async def callback(self, interaction: discord.Interaction):
        try:
            pid = int(self.values[0])
        except (ValueError, IndexError):
            await interaction.response.send_message("❌ Selecție invalidă.", ephemeral=True)
            return
        promoter = db.get_promoter(pid)
        if not promoter:
            await interaction.response.send_message("❌ Promoter inexistent.", ephemeral=True)
            return
        name = _display_name(interaction.guild, promoter)
        await interaction.response.send_message(
            f"**{name}** — alege acțiunea:", view=make_promoter_view(pid), ephemeral=True)


class LeaderboardView(discord.ui.View):
    def __init__(self, options=None):
        super().__init__(timeout=None)
        self.add_item(TierSelect(options))


# =========================================================
#  Cog
# =========================================================

class Leaderboard(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_dynamic_items(AccessButton, LikeButton, DislikeButton)
        self.bot.add_view(LeaderboardView())

    # ---- redare (tiere) ----
    async def regenerate_leaderboard(self, guild, channel, promoters=None):
        if promoters is None:
            promoters = db.list_promoters_sorted(guild.id)
        s = store.get_guild(guild.id)
        # șterge mesajele vechi (inclusiv formatul vechi, un-mesaj-per-promoter)
        for key in ("lb_tier_message_ids", "leaderboard_message_ids"):
            for mid in (s.get(key) or []):
                try:
                    m = await channel.fetch_message(mid)
                    await m.delete()
                except discord.HTTPException:
                    pass
        store.set_guild_value(guild.id, "leaderboard_message_ids", [])

        new_ids = []
        for (name, emoji, color, chunk, start) in build_tiers(promoters):
            msg = await channel.send(
                embed=build_tier_embed(guild, name, emoji, color, chunk, start),
                view=build_tier_view(guild, chunk, start))
            new_ids.append(msg.id)
        store.set_guild_value(guild.id, "lb_tier_message_ids", new_ids)

    async def refresh_leaderboard(self, guild):
        s = store.get_guild(guild.id)
        ch_id = s.get("leaderboard_channel_id")
        if not ch_id:
            return
        channel = guild.get_channel(ch_id)
        if channel is None:
            return
        promoters = db.list_promoters_sorted(guild.id)
        tiers = build_tiers(promoters)
        msg_ids = s.get("lb_tier_message_ids") or []
        # dacă s-a schimbat numărul de tiere (add/remove/urcări) → regenerăm
        if len(msg_ids) != len(tiers):
            await self.regenerate_leaderboard(guild, channel, promoters)
            return
        for i, (name, emoji, color, chunk, start) in enumerate(tiers):
            try:
                msg = await channel.fetch_message(msg_ids[i])
                await msg.edit(embed=build_tier_embed(guild, name, emoji, color, chunk, start),
                               view=build_tier_view(guild, chunk, start))
            except discord.NotFound:
                await self.regenerate_leaderboard(guild, channel, promoters)
                return

    # ---- comenzi ----
    group = app_commands.Group(
        name="promoter", description="Leaderboard promoteri",
        default_permissions=discord.Permissions(administrator=True),
    )

    @group.command(name="setup", description="Setează canalul clasamentului, rolul și categoria")
    @app_commands.describe(canal="Canalul clasamentului", rol="Rolul Promoter",
                           categorie="Categoria pentru canalele promoterilor (opțional)")
    async def setup_cmd(self, interaction: discord.Interaction, canal: discord.TextChannel,
                        rol: discord.Role, categorie: discord.CategoryChannel = None):
        store.set_guild_value(interaction.guild_id, "leaderboard_channel_id", canal.id)
        store.set_guild_value(interaction.guild_id, "promoter_role_id", rol.id)
        if categorie:
            store.set_guild_value(interaction.guild_id, "promoter_category_id", categorie.id)
        await interaction.response.defer(ephemeral=True)
        await self.regenerate_leaderboard(interaction.guild, canal)
        await interaction.followup.send(
            f"✅ Leaderboard setat în {canal.mention}. Rol: {rol.mention}.", ephemeral=True)

    @group.command(name="add", description="Adaugă un promoter (creează canal + rol)")
    @app_commands.describe(membru="Utilizatorul care devine promoter")
    async def add_cmd(self, interaction: discord.Interaction, membru: discord.Member):
        s = store.get_guild(interaction.guild_id)
        if not s.get("leaderboard_channel_id"):
            await interaction.response.send_message(
                "❌ Rulează întâi `/promoter setup`.", ephemeral=True)
            return
        if db.get_promoter_by_user(interaction.guild_id, membru.id):
            await interaction.response.send_message(
                "❌ Acest utilizator e deja promoter.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        category = guild.get_channel(s["promoter_category_id"]) if s.get("promoter_category_id") else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            membru: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
        }
        try:
            channel = await guild.create_text_channel(
                name=f"promoter-{membru.name}", overwrites=overwrites, category=category,
                reason="canal promoter")
        except discord.Forbidden:
            await interaction.followup.send(
                "❌ Nu am permisiunea «Manage Channels».", ephemeral=True)
            return

        role = guild.get_role(s["promoter_role_id"]) if s.get("promoter_role_id") else None
        if role:
            try:
                await membru.add_roles(role, reason="promoter")
            except discord.Forbidden:
                pass

        db.add_promoter(guild.id, membru.id, membru.display_name, channel.id)
        await self.refresh_leaderboard(guild)
        await interaction.followup.send(
            f"✅ {membru.mention} e acum promoter. Canal: {channel.mention}.", ephemeral=True)

    @group.command(name="remove", description="Scoate un promoter (șterge canal + rol)")
    @app_commands.describe(membru="Promoterul de scos")
    async def remove_cmd(self, interaction: discord.Interaction, membru: discord.Member):
        p = db.get_promoter_by_user(interaction.guild_id, membru.id)
        if not p:
            await interaction.response.send_message(
                "❌ Utilizatorul nu e promoter.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        if p.get("channel_id"):
            ch = guild.get_channel(p["channel_id"])
            if ch is not None:
                try:
                    await ch.delete(reason="promoter scos")
                except discord.HTTPException:
                    pass

        s = store.get_guild(guild.id)
        role = guild.get_role(s["promoter_role_id"]) if s.get("promoter_role_id") else None
        if role and role in membru.roles:
            try:
                await membru.remove_roles(role, reason="promoter scos")
            except discord.Forbidden:
                pass

        db.remove_promoter(p["id"])
        await self.refresh_leaderboard(guild)
        await interaction.followup.send(f"✅ {membru.mention} nu mai e promoter.", ephemeral=True)

    @group.command(name="regenereaza", description="Repostează clasamentul")
    async def regen_cmd(self, interaction: discord.Interaction):
        s = store.get_guild(interaction.guild_id)
        ch_id = s.get("leaderboard_channel_id")
        if not ch_id:
            await interaction.response.send_message("❌ Rulează întâi `/promoter setup`.", ephemeral=True)
            return
        channel = interaction.guild.get_channel(ch_id)
        if channel is None:
            await interaction.response.send_message("❌ Canalul salvat nu mai există.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await self.regenerate_leaderboard(interaction.guild, channel)
        await interaction.followup.send("✅ Clasament regenerat.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Leaderboard(bot))
