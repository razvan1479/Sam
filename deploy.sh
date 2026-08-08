#!/bin/bash
# deploy.sh — rulat automat de GitHub Actions la fiecare push pe main.
# Trage ultimul cod, instaleaza dependentele DOAR daca s-au schimbat,
# verifica faptul ca botul compileaza (plasa de siguranta), apoi reporneste.
set -e
cd ~/Sam

echo "==> Salvez hash-ul requirements dinainte"
OLD_REQ=$(sha1sum requirements.txt 2>/dev/null | cut -d' ' -f1 || echo "none")

echo "==> Trag ultimul cod de pe GitHub"
git fetch origin main
git reset --hard origin/main

echo "==> Verific daca requirements.txt s-a schimbat"
NEW_REQ=$(sha1sum requirements.txt 2>/dev/null | cut -d' ' -f1 || echo "none")
if [ "$OLD_REQ" != "$NEW_REQ" ]; then
    echo "    -> requirements s-au schimbat, instalez dependentele"
    .venv/bin/pip install -q -U -r requirements.txt
else
    echo "    -> requirements neschimbate, sar peste pip install (mai rapid)"
fi

echo "==> Verific ca fisierele Python compileaza"
# Daca ceva NU compileaza, set -e opreste scriptul AICI si botul ramane
# pornit pe codul vechi din memorie (nu reporneste cu cod stricat).
.venv/bin/python -m py_compile bot.py db.py store.py config.py dashboard.py cogs/*.py

echo "==> Repornesc botul"
sudo systemctl restart sam

echo "==> Gata! Status:"
sudo systemctl is-active sam
