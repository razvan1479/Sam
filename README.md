# Sam — Marketplace Metin2 (Discord bot)

Bot Discord modular (discord.py) pentru un marketplace anonim Metin2, cu sistem de
tickete și intermediar. Datele structurate stau în SQLite; setările per-server în JSON.

## Structura

```
Sam/
├── bot.py                # punctul de intrare (pornește botul, încarcă cog-urile)
├── config.py             # toate textele, culorile, emoji-urile (configurabile)
├── db.py                 # baza de date SQLite (anunțuri, tickete, blocări, statistici)
├── store.py              # setările per-server (canal, rol intermediar, categorie) în JSON
├── requirements.txt
├── cogs/
│   └── marketplace.py    # logica: panou, creare anunț, Contactează (+ butoane)
└── data/                 # se creează singur (marketplace.db, settings.json)
```

## Instalare

```bash
pip install -r requirements.txt
```

## Configurare bot (Discord Developer Portal)

1. Creează aplicația + botul, copiază **tokenul**.
2. Activează **Server Members Intent**.
3. Invită botul cu scope-urile `bot` + `applications.commands`.
4. Dă-i permisiunea **Manage Channels** (creează canalele de ticket).

## Pornire

1. Copiază `.env.example` în `.env` și completează `SAM_TOKEN` (și `GUILD_ID` pentru test).
2. `pip install -r requirements.txt`
3. `python bot.py`

`GUILD_ID` (ID-ul serverului tău) e opțional: dacă e setat, comenzile apar **instant** pe acel
server; dacă îl lași gol, se sincronizează global (poate dura până la ~1h).

## Comenzi de administrare

- `/marketplace setup canal:#... [rol_intermediar:@...] [categorie:...] [canal_loguri:#...]`
  Setează canalul, postează panoul și (opțional) rolul de intermediar, categoria ticketelor și canalul de loguri.
- `/marketplace panel` — regenerează mesajul permanent al panoului.
- `/marketplace delete anunt:<id>` — șterge un anunț și închide ticketele lui.
- `/marketplace stats [utilizator]` — statistici globale sau ale unui utilizator.
- `/marketplace logs [canal]` — setează sau arată canalul de loguri.
- `/marketplace blacklist utilizator:@... [motiv]` — restricționează un user de la marketplace.
- `/marketplace unblock utilizator:@...` — îl scoate de pe blacklist.
- `/marketplace reload` — reîncarcă modulul fără restart complet.

## Ce e implementat până acum

- Panoul permanent + butonul „Creează anunț" (persistent).
- Crearea anunțului (modal cu 5 câmpuri opționale) → embed anonim în canal.
- Contactează → validări + cooldown + ticket privat (cumpărător + intermediar + bot, fără autor)
  + DM către autor cu datele și statisticile cumpărătorului.
- Butoanele din DM: Vezi profil / Acceptă (adaugă autorul în ticket) / Refuză (închide ticketul)
  / Blochează (cu confirmare).
- Editează (formular precompletat, actualizează embed-ul) / Ridică (bump cu cooldown 24h, același ID).
- Finalizare schimb (doar intermediarul): arhivează ticketul, șterge anunțul, închide celelalte
  tickete pe acel anunț, +1 la „schimburi finalizate" pentru cumpărător și autor.
- Loguri: TOATE acțiunile se salvează în baza de date (vizibile în dashboard); pe Discord se
  trimite doar succesul (schimb finalizat). Anunțul are și buton de retragere (doar autorul).
- Comenzi admin: delete, stats (global / per user), logs, blacklist, unblock, reload.
- Raportări: buton în ticket (doar părțile) → formular → staff confirmă/respinge; doar rapoartele
  confirmate cresc contorul și apar în profil.
- Dashboard web (Flask, în același proces cu botul): fără login deocamdată. Pagini: overview,
  anunțuri (cu ștergere), tickete, blacklist (adaugă/scoate), loguri (toate acțiunile),
  calendar (canal, oră notificare, adaugă/șterge evenimente),
  bun venit / rămas bun (mesaj, titlu, culoare, embed/text). Pe `DASHBOARD_PORT` (implicit 5001).
- Bun venit / Rămas bun (`cogs/welcome_cog.py`): mesaj configurabil la intrare/ieșire, embed sau
  text, placeholdere `{user} {username} {server} {count}` — setat din dashboard.

## De făcut în continuare
- Login pe dashboard (înainte de a-l expune public pe Oracle).

---

## Funcția 2 — Calendar (cog)

Cog separat (`cogs/calendar_cog.py`) în același bot. Ține un calendar lunar într-un
mesaj fixat și trimite notificări `@everyone` zilnice. Fus orar: Europe/Bucharest.

- Un singur mesaj fixat cu calendarul lunii (ziua curentă în `[paranteze]`) + evenimentele
  de azi și cele viitoare, dedesubt. Se editează, nu se retrimite.
- Actualizare automată orară + la miezul nopții; evenimentele trecute se șterg automat.
- Notificare `@everyone` la ora configurată (implicit 08:00), un singur mesaj pe zi,
  ștearsă automat la 00:00 (ID salvat, rezistă la restart).
- Comenzi: `/adauga data ora descriere`, `/sterge id`, `/lista`, `/seteaza_canal`,
  `/seteaza_ora_notificare HH:MM`, `/regenereaza`.

Pornire: `/seteaza_canal #canal` → apare mesajul fixat. Apoi adaugi evenimente cu `/adauga`.

---

## Funcția 3 — Leaderboard promoteri (cog)

Cog (`cogs/leaderboard_cog.py`). Clasament de promoteri, **un mesaj per promoter**
(limita Discord: max 5 rânduri de butoane/mesaj, deci nu încap 8 într-unul singur).

- Fiecare promoter: `🥇 Nume  ❤️ likes | 💔 dislikes` + butoanele `[📂] [👍] [👎]`.
- 📂 — acces read-only 5 minute la canalul privat al promoterului (overwrite eliminat automat).
- 👍 / 👎 — un vot per user per promoter, schimbabil, fără auto-vot, cooldown 30s.
- Scor = like − dislike; la fiecare vot se recalculează, re-sortează și editează toate mesajele.
- `/promoter setup canal rol [categorie]` — configurează clasamentul.
- `/promoter add @user` — creează canal privat + dă rolul + adaugă în clasament.
- `/promoter remove @user` — șterge canalul + rolul + îl scoate din clasament.
- `/promoter regenereaza` — repostează clasamentul.
