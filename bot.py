# bot.py — punctul de intrare al botului Sam (marketplace Metin2)

import os
import threading
import discord
from discord.ext import commands
from dotenv import load_dotenv

import db
import dashboard

# Citește tokenul și (opțional) ID-ul serverului dintr-un fișier .env
load_dotenv()
TOKEN = os.getenv("SAM_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # opțional: pune-l pentru sincronizare INSTANT la test

INTENTS = discord.Intents.default()
INTENTS.members = True   # info despre membri (dată intrare pe server, cont creat etc.)
INTENTS.message_content = True   # necesar pentru releul anonim vânzător (citește mesajele din DM/ticket)


class SamBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS, help_command=None)

    async def setup_hook(self):
        db.init_db()
        await self.load_extension("cogs.marketplace")
        await self.load_extension("cogs.calendar_cog")
        await self.load_extension("cogs.welcome_cog")
        await self.load_extension("cogs.leaderboard_cog")

        if GUILD_ID:
            # sincronizare pe un singur server → comenzile apar imediat (ideal pentru test)
            guild = discord.Object(id=int(GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            # sincronizare globală → poate dura până la ~1h să apară
            await self.tree.sync()

        # Pornim dashboard-ul web într-un thread separat
        dashboard.set_bot(self)
        threading.Thread(target=dashboard.run_dashboard, daemon=True).start()
        print(f"[Sam] Dashboard pornit pe portul {os.getenv('DASHBOARD_PORT', '5001')}")

    async def on_ready(self):
        print(f"[Sam] Conectat ca {self.user} (ID: {self.user.id})")


def main():
    if not TOKEN:
        raise RuntimeError("Lipsește SAM_TOKEN. Creează un fișier .env (vezi .env.example).")
    SamBot().run(TOKEN)


if __name__ == "__main__":
    main()
