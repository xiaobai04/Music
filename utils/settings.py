"""读取与保存播放器的持久化用户设置。"""

import json
import os
import sys

BASE_DIR = getattr(sys, '_MEIPASS', os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
SETTINGS_FILE = os.path.join(BASE_DIR, 'user_settings.json')

DEFAULT_SETTINGS = {
    "device": "cuda",
    "play_mode": "顺序",
    "music_folder": "",
    "output_device": None,
    "mic_device": None,
    "mic_volume": 1.0,
    "mic_enabled": False,
    "vocal_volume": 1.0,
    "accomp_volume": 1.0,
    "lyric_font_size": 14,
    "queue": [],
    "history": [],
    "theme": "flatly",
    "language": "中文",
}

def load_settings():
    """从磁盘读取设置并与默认值合并。"""
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {**DEFAULT_SETTINGS, **data}
        except Exception:
            return DEFAULT_SETTINGS.copy()
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """将给定的设置字典写入磁盘。"""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
