# main.py
from ui.tkinter_ui import PlayerApp
import ttkbootstrap as ttkb

if __name__ == "__main__":
    root = ttkb.Window(themename="flatly")
    app = PlayerApp(root)
    root.mainloop()
