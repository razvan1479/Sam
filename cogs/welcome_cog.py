# cogs/welcome_cog.py — mesaje de BUN VENIT (la intrare) și RĂMAS BUN (la ieșire).
# Totul se configurează din dashboard. Necesită Server Members Intent (deja activat).
#
# Setări per server (chei în store): "welcome" și "goodbye", fiecare:
# {
#   "enabled": bool, "channel_id": int, "title": str, "message": str,
#   "use_embed": bool, "show_avatar": bool, "color": "#hex"
# }
# Placeholdere în titlu/mesaj: {user} {username} {server} {count}

import discord
from discord.ext import commands

import config
import store


def _fill(text, member) -> str:
    return (str(text or "")
            .replace("{user}", member.mention)
            .replace("{username}", getattr(member, "display_name", str(member)))
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count)))


def _color(value) -> discord.Color:
    try:
        return discord.Color(int(str(value).lstrip("#"), 16))
    except (ValueError, TypeError):
        return discord.Color(config.COLOR_INFO)


class WelcomeGoodbye(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send(self, member: discord.Member, cfg: dict, default_msg: str):
        if not cfg or not cfg.get("enabled") or not cfg.get("channel_id"):
            return
        channel = member.guild.get_channel(int(cfg["channel_id"]))
        if channel is None:
            return

        message = _fill(cfg.get("message") or default_msg, member)
        mentions = discord.AllowedMentions(users=True)

        if cfg.get("use_embed", True):
            embed = discord.Embed(description=message, color=_color(cfg.get("color")))
            if cfg.get("title"):
                embed.title = _fill(cfg.get("title"), member)
            if cfg.get("show_avatar", True):
                embed.set_thumbnail(url=member.display_avatar.url)
            try:
                await channel.send(embed=embed, allowed_mentions=mentions)
            except discord.HTTPException:
                pass
        else:
            try:
                await channel.send(message, allowed_mentions=mentions)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = store.get_guild(member.guild.id).get("welcome", {})
        await self._send(member, cfg, "Bine ai venit, {user}! Acum suntem {count} membri. 🎉")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = store.get_guild(member.guild.id).get("goodbye", {})
        await self._send(member, cfg, "{username} a părăsit serverul. Rămânem {count} membri.")


async def setup(bot: commands.Bot):
    await bot.add_cog(WelcomeGoodbye(bot))
