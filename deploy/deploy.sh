#!/bin/bash
# Rulează pe server ca să iei ultima versiune și să repornești botul.
set -e
cd ~/Sam
git pull
.venv/bin/pip install -U -r requirements.txt
sudo systemctl restart sam
echo "✅ Sam deployat și repornit."
