"""Playlist management mixin handling music selection and queue."""

import os
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
import threading


class PlaylistMixin:
    """Mixin providing playlist and queue management methods."""

    def choose_folder(self):
        """Prompt the user to select a music folder and load it."""
        folder = filedialog.askdirectory()
        if folder:
            self.load_folder(folder)
            self.persist_settings()

    def load_folder(self, folder):
        """Load all supported music files from the given folder."""
        self.music_folder = folder
        self.all_music_files = [
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith((".mp3", ".flac"))
        ]
        self.all_music_files.sort()
        self.search_var.set("")
        self.music_files = list(self.all_music_files)
        self.refresh_file_listbox()
        self.update_queue_listbox()

    def refresh_file_listbox(self):
        """Refresh the listbox displaying available songs."""
        self.file_listbox.delete(0, tk.END)
        for f in self.music_files:
            self.file_listbox.insert(tk.END, os.path.basename(f))

    def update_queue_listbox(self):
        """Redraw the queue list to match the current state."""
        for child in self.queue_list_frame.winfo_children():
            child.destroy()
        if not self.future_queue:
            ttk.Label(
                self.queue_list_frame,
                text="(空)",
                font=("Microsoft YaHei", 10),
            ).pack()
        else:
            for idx, p in enumerate(self.future_queue):
                row = ttk.Frame(self.queue_list_frame)
                row.pack(fill="x")
                ttk.Label(
                    row,
                    text=os.path.basename(p),
                    font=("Microsoft YaHei", 10),
                ).pack(side=tk.LEFT, fill="x", expand=True)
                ttk.Button(
                    row,
                    text="删除",
                    command=lambda i=idx: self.remove_from_queue(i),
                    bootstyle="danger",
                ).pack(side=tk.RIGHT)

    def clear_queue(self):
        """Remove all songs from the upcoming queue."""
        if self.future_queue:
            self.future_queue.clear()
            self.update_queue_listbox()
            self.persist_settings()

    def remove_from_queue(self, index):
        """Remove the song at the specified queue index."""
        if 0 <= index < len(self.future_queue):
            removed = self.future_queue.pop(index)
            self.lyrics_box.insert(
                "end", f"❌ 已移除：{os.path.basename(removed)}\n"
            )
            self.update_queue_listbox()
            self.persist_settings()

    def toggle_queue(self):
        """Show or hide the upcoming queue panel."""
        if self.queue_visible:
            self.queue_content.grid_remove()
            self.queue_visible = False
            self.toggle_queue_button.config(text="显示待播列表")
        else:
            self.queue_content.grid(row=1, column=0, sticky="ew", pady=2)
            self.queue_visible = True
            self.toggle_queue_button.config(text="隐藏待播列表")


    def on_song_double_click(self, event):
        """Handle double clicking on a song in the listbox."""
        index = self.file_listbox.curselection()
        if not index:
            return
        self.auto_next_enabled = False
        if self.player:
            self.player.stop()
            self.player = None
        self.current_index = index[0]
        threading.Thread(
            target=lambda: self.play_song(self.current_index), daemon=True
        ).start()

    def add_to_queue(self):
        """Add the currently selected song to the queue."""
        index = self.file_listbox.curselection()
        if not index:
            return
        path = self.music_files[index[0]]
        self.future_queue.append(path)
        self.lyrics_box.insert(
            "end", f"✅ 已加入待播：{os.path.basename(path)}\n"
        )
        self.update_queue_listbox()
        self.persist_settings()

