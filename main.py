import sys
import logging

sys.setrecursionlimit(10000)  # 临时调高避免 RecursionError
logging.basicConfig(level=logging.DEBUG)

# main.py
from ui.tkinter_ui import PlayerApp
import tkinter as tk

if __name__ == "__main__":
    root = tk.Tk()
    app = PlayerApp(root)
    root.mainloop()
