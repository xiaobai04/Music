import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'user_settings.json')

DEFAULT_SETTINGS = {
    "device": "cuda",
    "play_mode": "顺序",
    "last_folder": ""
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {**DEFAULT_SETTINGS, **data}
        except Exception:
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
