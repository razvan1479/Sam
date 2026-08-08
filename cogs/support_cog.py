# cogs/support_cog.py — tichete de SUPORT / CERERE, separate de marketplace.
# Panou cu două butoane (Suport / Cerere) → creează tichet privat în categoria de suport,
# vizibil pentru user + rolul de suport. NU e anonim (e suport normal).

import asyncio

import discord
from discord import app_commands
from discord.ext import commands

import config
import db
import store


async def _close_channel_later(channel: discord.TextChannel, secs: int):
    await asyncio.sleep(secs)
    try:
        await channel.delete(reason="tichet suport închis")
    except discord.HTTPException:
        pass


# ---------------- Butoane ----------------

class OpenSupportButton(discord.ui.DynamicItem[discord.ui.Button],
                        template=config.CID_SUPPORT_OPEN + r":(?P<kind>[a-z]+)"):
    def __init__(self, kind: str):
        self.kind = kind
        label = config.SUPPORT_BTN_SUPORT if kind == "suport" else config.SUPPORT_BTN_CERERE
        style = discord.ButtonStyle.primary if kind == "suport" else discord.ButtonStyle.secondary
        super().__init__(discord.ui.Button(label=label, style=style,
                                           custom_id=f"{config.CID_SUPPORT_OPEN}:{kind}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(match["kind"])

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        s = store.get_guild(guild.id)
        category = guild.get_channel(s["support_category_id"]) if s.get("support_category_id") else None
        role = guild.get_role(s["support_role_id"]) if s.get("support_role_id") else None

        if db.has_open_support_ticket(guild.id, interaction.user.id):
            await interaction.response.send_message(config.SUPPORT_ALREADY_OPEN, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True, manage_channels=True),
        }
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True)

        try:
            channel = await guild.create_text_channel(
                name=f"{self.kind}-{interaction.user.name}", overwrites=overwrites,
                category=category, reason="tichet suport")
        except discord.Forbidden:
            await interaction.followup.send("❌ Nu am permisiunea «Manage Channels».", ephemeral=True)
            return

        tid = db.create_support_ticket(guild.id, interaction.user.id, channel.id, self.kind)
        await channel.send(
            config.SUPPORT_WELCOME.format(
                kind=self.kind, user=interaction.user.mention, role=(role.mention if role else "")),
            view=make_close_view(tid),
        )
        await interaction.followup.send(
            config.SUPPORT_CREATED.format(channel=channel.mention), ephemeral=True)


class CloseSupportButton(discord.ui.DynamicItem[discord.ui.Button],
                         template=config.CID_SUPPORT_CLOSE + r":(?P<tid>[0-9]+)"):
    def __init__(self, ticket_id: int):
        self.ticket_id = ticket_id
        super().__init__(discord.ui.Button(
            label=config.SUPPORT_BTN_CLOSE, style=discord.ButtonStyle.danger,
            custom_id=f"{config.CID_SUPPORT_CLOSE}:{ticket_id}"))

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["tid"]))

    async def callback(self, interaction: discord.Interaction):
        ticket = db.get_support_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ Tichet inexistent.", ephemeral=True)
            return
        member = interaction.user
        role_id = store.get_guild(interaction.guild_id).get("support_role_id")
        allowed = (member.id == ticket["user_id"]
                   or member.guild_permissions.administrator
                   or (role_id and any(r.id == role_id for r in member.roles)))
        if not allowed:
            await interaction.response.send_message(config.SUPPORT_ONLY_STAFF, ephemeral=True)
            return
        db.set_support_ticket_status(ticket["id"], "closed")
        await interaction.response.send_message(config.SUPPORT_CLOSING)
        asyncio.create_task(_close_channel_later(interaction.channel, 5))


def make_panel_view() -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(OpenSupportButton("suport"))
    view.add_item(OpenSupportButton("cerere"))
    return view


def make_close_view(ticket_id: int) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(CloseSupportButton(ticket_id))
    return view


# ---------------- Cog ----------------

class Support(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_dynamic_items(OpenSupportButton, CloseSupportButton)

    async def post_panel(self, channel: discord.TextChannel):
        embed = discord.Embed(title=config.SUPPORT_PANEL_TITLE,
                              description=config.SUPPORT_PANEL_DESC, color=config.COLOR_PRIMARY)
        msg = await channel.send(embed=embed, view=make_panel_view())
        store.set_guild_value(channel.guild.id, "support_panel_channel_id", channel.id)
        store.set_guild_value(channel.guild.id, "support_panel_message_id", msg.id)

    group = app_commands.Group(
        name="support", description="Tichete de suport / cerere",
        default_permissions=discord.Permissions(administrator=True),
    )

    @group.command(name="setup", description="Configurează suportul (canal panou, rol, categorie)")
    @app_commands.describe(canal="Canalul unde apare panoul", rol="Rolul echipei de suport",
                           categorie="Categoria în care se creează tichetele")
    async def setup_cmd(self, interaction: discord.Interaction, canal: discord.TextChannel,
                        rol: discord.Role, categorie: discord.CategoryChannel):
        gid = interaction.guild_id
        store.set_guild_value(gid, "support_role_id", rol.id)
        store.set_guild_value(gid, "support_category_id", categorie.id)
        await interaction.response.defer(ephemeral=True)
        await self.post_panel(canal)
        await interaction.followup.send(
            f"✅ Suport configurat. Panou în {canal.mention}, rol {rol.mention}, categorie **{categorie.name}**.",
            ephemeral=True)

    @group.command(name="panel", description="Repostează panoul de suport")
    async def panel_cmd(self, interaction: discord.Interaction):
        s = store.get_guild(interaction.guild_id)
        ch_id = s.get("support_panel_channel_id")
        channel = interaction.guild.get_channel(ch_id) if ch_id else interaction.channel
        await interaction.response.defer(ephemeral=True)
        await self.post_panel(channel)
        await interaction.followup.send("✅ Panou repostat.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Support(bot))
