# store.py — stocare simplă (JSON) pentru SETĂRI: canal marketplace, id-ul mesajului panou etc.
# Datele „grele" (anunțuri, tickete, useri) vor merge într-o bază de date reală în pasul următor.

import json
import os
import threading

_PATH = os.path.join(os.path.dirname(__file__), "data", "settings.json")
_lock = threading.Lock()


def _load() -> dict:
    if not os.path.exists(_PATH):
        return {}
    with open(_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_PATH), exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_guild(guild_id: int) -> dict:
    """Întoarce setările unui server (dict gol dacă nu există)."""
    with _lock:
        return _load().get(str(guild_id), {})


def set_guild_value(guild_id: int, key: str, value) -> None:
    """Salvează o singură setare pentru un server."""
    with _lock:
        data = _load()
        data.setdefault(str(guild_id), {})[key] = value
        _save(data)


def first_guild_id():
    """Primul server configurat (folosit de dashboard pentru acțiuni). None dacă nu există."""
    with _lock:
        for key in _load().keys():
            try:
                return int(key)
            except ValueError:
                continue
    return None
