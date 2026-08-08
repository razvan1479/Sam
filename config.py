# config.py — toate textele, culorile și emoji-urile configurabile
# Le modifici de aici, fără să te atingi de logica botului.

# ---- Culori (hex) ----
COLOR_PRIMARY  = 0x2ecc71   # verde  — disponibil / succes
COLOR_INFO     = 0x3498db   # albastru — informativ (panoul)
COLOR_WARNING  = 0xf1c40f   # galben
COLOR_DANGER   = 0xe74c3c   # roșu   — refuz / eroare
COLOR_NEUTRAL  = 0x2b2d31   # gri închis

# ---- Emoji ----
EMOJI_CREATE    = "➕"
EMOJI_ANNOUNCE  = "🔄"
EMOJI_CONTACT   = "📩"
EMOJI_EDIT      = "✏️"
EMOJI_BUMP      = "📌"
EMOJI_AVAILABLE = "🟢"

# ---- Panoul permanent din canalul de marketplace ----
PANEL_TITLE = "Marketplace Metin2"
PANEL_DESCRIPTION = (
    "Creează un anunț **anonim** pe piața comunității.\n\n"
    "• Toate schimburile se desfășoară prin **intermediari**.\n"
    "• Citește regulamentul înainte de utilizare.\n"
    "• Apasă butonul de mai jos pentru a crea un anunț."
)
PANEL_FOOTER = "Marketplace Metin2"
PANEL_BUTTON_LABEL = "Creează anunț"

# ---- custom_id-uri (NU le schimba după deploy — butoanele vechi nu ar mai răspunde) ----
CID_CREATE = "mkt:create"

# custom_id-uri pentru butoanele de pe fiecare anunț (au ID-ul anunțului lipit la final)
CID_CONTACT = "mkt:contact"
CID_EDIT    = "mkt:edit"
CID_BUMP    = "mkt:bump"

# ---- Modalul de creare anunț ----
MODAL_TITLE = "Creează anunț"

# ---- Butoanele de pe anunț ----
BTN_CONTACT = "Contactează"
BTN_EDIT    = "Editează"
BTN_BUMP    = "Ridică anunțul"

# ---- Embed-ul unui anunț ----
ANN_TITLE            = "Anunț #{id}"   # {id} = numărul anunțului
ANN_STATUS_AVAILABLE = "🟢 Disponibil"
ANN_FOOTER           = "Marketplace Metin2"
F_SERVER_FROM = "Server"
F_SERVER_TO   = "Server pe care doresc"
F_OFFER       = "Oferă"
F_WANT        = "Caută"
F_STATUS      = "Status"
F_DATE        = "Publicat"


# =========================================================
#  FUNCȚIA 3 — Contactează (ticket + DM către autor)
# =========================================================

# ---- Mesaje de validare la apăsarea „Contactează" ----
MSG_CANNOT_CONTACT_OWN = "❌ Nu poți contacta propriul anunț."
MSG_ALREADY_TICKET     = "❌ Ai deja o solicitare activă pentru acest anunț."
MSG_BLOCKED            = "❌ Nu poți deschide un ticket pentru anunțurile acestui vânzător."
MSG_ANN_UNAVAILABLE    = "❌ Anunțul nu mai este disponibil."
MSG_NO_INTERMEDIAR     = "⚠️ Adminul nu a configurat încă rolul de intermediar, dar ticketul a fost creat."

# ---- Ticket ----
TICKET_NAME    = "ticket-{ann_id}-{user}"   # numele canalului de ticket
TICKET_WELCOME = (
    "🎟️ Ticket pentru anunțul **#{ann_id}**.\n"
    "Intermediarul vă va asista pe parcursul schimbului. Vânzătorul a fost anunțat în privat."
)
TICKET_AUTHOR_NO_DM = (
    "⚠️ Nu am putut trimite notificarea în privat vânzătorului (are DM-urile închise)."
)
MSG_TICKET_CREATED  = "✅ Ticket creat: {channel}. Vânzătorul a fost notificat."

# ---- DM-ul primit de autor ----
DM_TITLE        = "Cerere nouă pentru anunțul #{ann_id}"
DM_F_USER       = "👤 Utilizator"
DM_F_ID         = "🆔 ID Discord"
DM_F_ACCOUNT    = "📅 Cont Discord creat"
DM_F_JOINED     = "📥 Membru pe server din"
DM_F_COMPLETED  = "⭐ Schimburi finalizate"
DM_F_CANCELLED  = "❌ Schimburi anulate"
DM_F_REPORTS    = "🚫 Raportări confirmate"
DM_F_TICKET     = "🎟️ Ticket ID"

# ---- Butoanele din DM ----
BTN_PROFILE = "Vezi profil"
BTN_ACCEPT  = "Acceptă"
BTN_REFUSE  = "Refuză"
BTN_BLOCK   = "Blochează utilizatorul"

EMOJI_PROFILE = "📄"
EMOJI_ACCEPT  = "✅"
EMOJI_REFUSE  = "❌"
EMOJI_BLOCK   = "⛔"

CID_TPROFILE = "mkt:tprofile"
CID_TACCEPT  = "mkt:taccept"
CID_TREFUSE  = "mkt:trefuse"
CID_TBLOCK   = "mkt:tblock"

# ---- Cooldown anti-spam la „Contactează" (secunde, per utilizator) ----
CONTACT_COOLDOWN_SECONDS = 30
MSG_COOLDOWN = "⏳ Prea repede — mai așteaptă {seconds}s înainte de a deschide alt ticket."


# =========================================================
#  FUNCȚIA 4 — butoanele din DM (profil / acceptă / refuză / blochează)
# =========================================================

# ---- Vezi profil ----
PROFILE_TITLE       = "Profil Marketplace"
PROFILE_F_USER      = "👤 Utilizator"
PROFILE_F_ID        = "🆔 ID Discord"
PROFILE_F_ACCOUNT   = "📅 Cont Discord creat"
PROFILE_F_JOINED    = "📥 Membru pe server din"
PROFILE_F_TIME      = "⏱️ Timp petrecut pe server"
PROFILE_STATS       = "📊 Statistici"
PROFILE_F_COMPLETED = "✔️ Schimburi finalizate"
PROFILE_F_CANCELLED = "❌ Schimburi anulate"
PROFILE_F_REPORTS   = "🚫 Raportări confirmate"

# ---- Acceptă / Refuză ----
MSG_ACCEPTED_TICKET = "✅ Vânzătorul a acceptat cererea. Scrieți aici — el răspunde **anonim**, prin bot."
MSG_ACCEPTED_AUTHOR = "✅ Ai acceptat cererea. Scrie mesajele **aici, în DM** — apar anonim în ticket. Rămâi complet anonim."
MSG_REFUSED_BUYER   = "❌ Vânzătorul a refuzat solicitarea."
MSG_REFUSED_AUTHOR  = "Ai refuzat solicitarea. Ticketul se închide."
MSG_TICKET_CLOSING  = "🔒 Ticketul se închide în câteva secunde..."
TICKET_CLOSE_DELAY  = 6   # secunde până la ștergerea canalului

# ---- Blochează ----
MSG_BLOCK_CONFIRM     = "Sigur vrei să blochezi acest utilizator? Nu va mai putea deschide tickete pentru anunțurile tale."
MSG_BLOCKED_DONE      = "⛔ Utilizator blocat. Nu mai poate deschide tickete pentru anunțurile tale."
MSG_BLOCK_CANCELLED   = "Anulat."
BTN_CONFIRM = "Confirmă"
BTN_CANCEL  = "Anulează"

# ---- Comune ----
MSG_TICKET_ALREADY_HANDLED = "ℹ️ Acest ticket a fost deja procesat."
MSG_NOT_AUTHOR             = "❌ Doar autorul anunțului poate face asta."


# =========================================================
#  FUNCȚIA 5 — Editează / Ridică
# =========================================================
EDIT_MODAL_TITLE = "Editează anunțul"
MSG_ANN_UPDATED  = "✅ Anunț actualizat."

BUMP_COOLDOWN_HOURS = 24
MSG_BUMP_DONE       = "📌 Anunț ridicat."
MSG_BUMP_COOLDOWN   = "⏳ Poți ridica anunțul din nou peste {time}."


# =========================================================
#  FUNCȚIA 6 — Finalizare schimb (doar intermediarul)
# =========================================================
BTN_FINALIZE   = "Marchează schimbul ca finalizat"
EMOJI_FINALIZE = "✅"
CID_FINALIZE   = "mkt:finalize"

TICKET_FINALIZE_HINT = "Când schimbul e gata, **intermediarul** îl marchează finalizat cu butonul de mai jos."
MSG_FINALIZE_DONE    = "✅ Schimb finalizat. Ticketul a fost arhivat."
MSG_FINALIZE_OTHERS  = "Anunțul nu mai este disponibil deoarece schimbul a fost finalizat."
MSG_ONLY_INTERMEDIAR = "❌ Doar intermediarul poate finaliza schimbul."
MSG_TICKET_CLOSED    = "ℹ️ Ticketul este deja închis."
ARCHIVE_NAME         = "arhiva-{ann_id}"


# =========================================================
#  FUNCȚIA 7 — Loguri
# =========================================================
LOG_ANN_CREATED   = "📝 Anunț creat"
LOG_ANN_EDITED    = "✏️ Anunț editat"
LOG_ANN_BUMPED    = "📌 Anunț ridicat"
LOG_ANN_DELETED   = "🗑️ Anunț șters"
LOG_TICKET_OPEN   = "🎟️ Ticket creat"
LOG_TICKET_CLOSED = "🔒 Ticket închis"
LOG_ACCEPTED      = "✅ Cerere acceptată"
LOG_REFUSED       = "❌ Cerere refuzată"
LOG_BLOCKED       = "⛔ Utilizator blocat"
LOG_FINALIZED     = "🤝 Schimb finalizat"
LOG_REPORT        = "🚨 Raport confirmat"


# =========================================================
#  FUNCȚIA 8 — Comenzi admin (delete / stats / logs / blacklist / unblock / reload)
# =========================================================
MSG_GLOBAL_BLOCKED     = "❌ Ai fost restricționat de la marketplace de către staff."
MSG_ANN_REMOVED_TICKET = "Anunțul a fost șters de administrație. Ticketul se închide."
LOG_BLACKLIST          = "⛔ Blacklist"


# =========================================================
#  FUNCȚIA 9 — Raportări (confirmate de staff)
# =========================================================
BTN_REPORT         = "Raportează"
EMOJI_REPORT       = "🚨"
CID_REPORT         = "mkt:report"
CID_REPORT_OK      = "mkt:reportok"
CID_REPORT_NO      = "mkt:reportno"

REPORT_MODAL_TITLE = "Raportează utilizatorul"
TICKET_CONTROLS_HINT = "🔧 Intermediarul poate finaliza schimbul. Părțile pot raporta un abuz."

MSG_REPORT_SENT           = "✅ Raport trimis către staff."
MSG_REPORT_ONLY_PARTIES   = "❌ Doar părțile din schimb pot raporta."
MSG_REPORT_NOT_CONFIGURED = "⚠️ Raportările nu sunt configurate (staff trebuie să seteze un canal de loguri)."
MSG_ONLY_STAFF            = "❌ Doar staff-ul poate face asta."
MSG_REPORT_HANDLED        = "ℹ️ Raportul a fost deja procesat."

REPORT_TITLE      = "🚨 Raport nou"
REPORT_F_REPORTER = "Reclamant"
REPORT_F_REPORTED = "Reclamat"
REPORT_F_REASON   = "Motiv"
BTN_REPORT_CONFIRM = "Confirmă raport"
BTN_REPORT_REJECT  = "Respinge"
MSG_REPORT_CONFIRMED = "✅ Raport confirmat. Contorul reclamatului a crescut."
MSG_REPORT_REJECTED  = "❌ Raport respins."


# =========================================================
#  Retragere anunț (de către autor) + loguri doar cu succese
# =========================================================
BTN_WITHDRAW             = "Retrage anunțul"
EMOJI_WITHDRAW           = "🗑️"
CID_WITHDRAW             = "mkt:withdraw"
MSG_ANN_WITHDRAWN        = "✅ Anunțul a fost retras."
MSG_ANN_WITHDRAWN_TICKET = "Anunțul a fost retras de autor. Ticketul se închide."

LOG_ANN_WITHDRAWN = "🗑️ Anunț retras"

# Linie divizoare care lățește și înfrumusețează cardul de anunț (regleaz-o cum vrei)
ANN_DIVIDER = "\u2500" * 20

RELAY_SELLER_NAME = "Vânzător (anonim)"


# =========================================================
#  Texte calendar (configurabile din dashboard)
# =========================================================
CAL_TODAY_LABEL    = "📍 Astăzi"
CAL_UPCOMING_LABEL = "📌 Următoarele evenimente"
CAL_EMPTY_LABEL    = "✅ Nu există evenimente programate."
CAL_NOTIFY_HEADER  = "📅 Evenimentele de astăzi"

# Câte zile de loguri se păstrează (restul se șterg automat, o dată pe zi)
LOG_KEEP_DAYS = 30
