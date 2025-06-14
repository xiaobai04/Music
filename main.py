# main.py
from ui.tkinter_ui import PlayerApp
import tkinter as tk

if __name__ == "__main__":
    root = tk.Tk()
    app = PlayerApp(root)
    root.mainloop()
