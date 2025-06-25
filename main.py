"""程序入口：启动基于 Tkinter 的音乐播放器。"""

import os
from ui.tkinter_ui import PlayerApp
import ttkbootstrap as ttkb
from utils.settings import load_settings

# 仅在直接运行此文件时启动图形界面
if __name__ == "__main__":
    # 读取之前保存的主题设置
    settings = load_settings()
    theme = settings.get("theme", "flatly")

    root = ttkb.Window(themename=theme)

    # 绝对/相对皆可，这里示例相对路径
    ico_path = os.path.join(os.path.dirname(__file__), "img", "ico", "ico.ico")
    root.iconbitmap(ico_path)

    app = PlayerApp(root)
    root.mainloop()
