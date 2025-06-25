import os
from ui.tkinter_ui import PlayerApp
import ttkbootstrap as ttkb
from utils.settings import load_settings

if __name__ == "__main__":
    settings = load_settings()
    theme = settings.get("theme", "flatly")

    root = ttkb.Window(themename=theme)

    # 绝对/相对皆可，这里示例相对路径
    ico_path = os.path.join(os.path.dirname(__file__), "img", "ico", "ico.ico")
    root.iconbitmap(ico_path)

    app = PlayerApp(root)
    root.mainloop()
