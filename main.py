# main.py
from ui.tkinter_ui import PlayerApp
import ttkbootstrap as ttkb
from utils.settings import load_settings

if __name__ == "__main__":
    settings = load_settings()
    theme = settings.get("theme", "flatly")
    root = ttkb.Window(themename=theme)
    app = PlayerApp(root)
    root.mainloop()
