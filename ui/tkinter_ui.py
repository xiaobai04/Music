import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import ttkbootstrap as ttkb
import threading
import time
import os
import random
import uuid
import platform
import sounddevice as sd
import torch
import torchaudio
try:
    import soundfile as sf
except Exception:
    sf = None

from utils.settings import load_settings, save_settings
from utils.audio_utils import resample_audio

from audio.separator import separate_audio_in_memory
from audio.player import AudioPlayer
from lyrics.lrc_parser import parse_lrc
from lyrics.lyrics_display import start_lyrics_display


class PlayerApp:
    def __init__(self, root):
        # ================= 基础初始化 ================= #
        self.root = root
        self.root.title("🎵 人声分离播放器")
        self.root.geometry("1200x720")

        # ——— 主题与持久化设置 ——— #
        style = ttkb.Style()
        self.style = style
        settings = load_settings()

        self.theme_choice   = tk.StringVar(value=settings.get("theme", "flatly"))
        self.language_choice = tk.StringVar(value=settings.get("language", "中文"))
        self.progress_map    = dict(settings.get("progress", {}))
        self.style.theme_use(self.theme_choice.get())
        self.theme_choice.trace_add("write",
                                    lambda *_: self.style.theme_use(self.theme_choice.get()))

        # ——— 音频相关状态变量 ——— #
        sd.default.latency = "low"
        if platform.system() == "Windows":
            for idx, api in enumerate(sd.query_hostapis()):
                if "WASAPI" in api.get("name", ""):
                    try:
                        sd.default.hostapi = idx
                    except AttributeError:
                        pass
                    in_dev, out_dev = api.get("default_input_device", -1), api.get("default_output_device", -1)
                    cur_in, cur_out = sd.default.device
                    sd.default.device = (in_dev if in_dev >= 0 else cur_in,
                                        out_dev if out_dev >= 0 else cur_out)
                    break

        self.audio_path      = None
        self.player          = None
        self.device_choice   = tk.StringVar(value=settings.get("device", "cuda"))
        self.play_mode       = tk.StringVar(value=settings.get("play_mode", "顺序"))
        self.music_folder    = settings.get("music_folder", "")
        self.output_device   = tk.StringVar(value=settings.get("output_device", "默认"))
        self.mic_device      = tk.StringVar(value=settings.get("mic_device", "无"))
        self.output_device_map, self.input_device_map = {}, {}
        self.mic_volume      = tk.DoubleVar(value=settings.get("mic_volume", 1.0))
        self.vocal_volume    = tk.DoubleVar(value=settings.get("vocal_volume", 1.0))
        self.accomp_volume   = tk.DoubleVar(value=settings.get("accomp_volume", 1.0))
        self.mic_enabled     = tk.BooleanVar(value=settings.get("mic_enabled", False))
        self.update_loop_running = False
        self.dragging            = False
        self.music_files, self.all_music_files = [], []
        self.current_index       = -1
        self.next_audio_data = self.prev_audio_data = self.current_audio_data = None
        self.future_queue        = list(settings.get("queue", []))
        raw_hist = list(settings.get("history", []))
        self.play_history        = []
        for item in raw_hist:
            if isinstance(item, dict) and 'path' in item:
                self.play_history.append(item)
            elif isinstance(item, str):
                self.play_history.append({'path': item, 'time': 0})
        self.history_limit       = 100
        self.session_id          = None

        # ========= 全局快捷键 ========= #
        root.bind('<space>', lambda e: self.toggle_pause())
        root.bind('<Left>',  lambda e: self.seek_relative(-5))
        root.bind('<Right>', lambda e: self.seek_relative(5))
        root.bind('<Up>',    lambda e: self.adjust_volume(0.05))
        root.bind('<Down>',  lambda e: self.adjust_volume(-0.05))
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # ================= 主容器：左右两栏 ================= #
        main = ttk.Frame(root)
        main.pack(fill="both", expand=True)

        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=3)
        main.rowconfigure(0,  weight=1)

        # ================= 左栏 ================= #
        left_frame = ttk.Frame(main, padding=(10, 10))
        left_frame.grid(row=0, column=0, sticky="nsew")
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(3, weight=1)

        ttk.Button(left_frame, text="选择音乐文件夹",
                command=self.choose_folder, bootstyle="info-outline")\
            .grid(row=0, column=0, sticky="ew", pady=(0, 8))

        search_row = ttk.Frame(left_frame)
        search_row.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        search_row.columnconfigure(0, weight=1)
        self.search_var   = tk.StringVar()
        self.search_entry = tk.Entry(search_row, textvariable=self.search_var,
                                    font=("Microsoft YaHei", 11))
        self.search_entry.grid(row=0, column=0, sticky="ew")
        self.search_entry.bind("<Return>", lambda e: self.search_songs())
        ttk.Button(search_row, text="搜索", command=self.search_songs,
                bootstyle="secondary", width=6).grid(row=0, column=1, padx=(6, 0))

        ttk.Label(left_frame, text="🎵 音乐列表", font=("Microsoft YaHei", 11, "bold"))\
            .grid(row=2, column=0, sticky="w")
        self.file_listbox = tk.Listbox(left_frame, font=("Microsoft YaHei", 11))
        self.file_listbox.grid(row=3, column=0, sticky="nsew")
        self.file_listbox.bind("<Double-Button-1>", self.on_song_double_click)

        ttk.Button(left_frame, text="加入播放列表", command=self.add_to_queue,
                bootstyle="success").grid(row=4, column=0, sticky="e", pady=(6, 0))

        # ================= 右栏 ================= #
        right_frame = ttk.Frame(main, padding=(10, 10))
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(right_frame)
        notebook.grid(row=0, column=0, sticky="nsew")
        ctrl_tab  = ttk.Frame(notebook)
        lyric_tab = ttk.Frame(notebook)
        notebook.add(ctrl_tab,  text="控制")
        notebook.add(lyric_tab, text="歌词")

        ctrl_tab.columnconfigure(0, weight=1)

        self.current_file_label = ttk.Label(ctrl_tab, text="当前播放：",
                                            font=("Microsoft YaHei", 12, "bold"))
        self.current_file_label.grid(row=0, column=0, sticky="w", pady=(2, 6))

        # ====== 音频设置（优化居中） ====== #
        audio_frame = ttk.Labelframe(ctrl_tab, text="音频设置")
        audio_frame.grid(row=1, column=0, sticky="ew", padx=2, pady=2)

        # 查询设备信息
        self.output_device_map.clear()
        self.input_device_map.clear()
        all_devices = list(enumerate(sd.query_devices()))
        hostapis    = sd.query_hostapis()

        output_devs = []
        for i, dev in all_devices:
            if dev['max_output_channels'] > 0:
                label = f"{i}: {dev['name']} ({hostapis[dev['hostapi']]['name']})"
                output_devs.append(label)
                self.output_device_map[label] = i
        if not output_devs:
            output_devs = ["默认"]
            self.output_device_map["默认"] = None
        if self.output_device.get() not in output_devs:
            self.output_device.set("默认")

        input_devs = []
        for i, dev in all_devices:
            if dev['max_input_channels'] > 0:
                label = f"{i}: {dev['name']} ({hostapis[dev['hostapi']]['name']})"
                input_devs.append(label)
                self.input_device_map[label] = i
        if not input_devs:
            input_devs = ["无"]
            self.input_device_map["无"] = None
        if self.mic_device.get() not in input_devs:
            self.mic_device.set("无")

        # --- 行1：分离方式 + 播放模式 ---
        row1 = ttk.Frame(audio_frame)
        row1.pack(pady=4)
        ttk.Label(row1, text="分离方式：").pack(side="left", padx=4)
        option_menu1 = tk.OptionMenu(row1, self.device_choice, "cpu", "cuda")
        option_menu1.config(
            bg="#3498DB",        # 背景色（淡蓝色）
            fg="white",          # 字体颜色
            activebackground="#48A2DE",
            activeforeground="white",
            highlightthickness=0,
            relief="flat"
        )
        option_menu1["menu"].config(
            bg="white",          # 下拉菜单背景
            fg="black"           # 下拉菜单文字颜色
        )
        option_menu1.pack(side="left", padx=4)

        ttk.Label(row1, text="播放模式：").pack(side="left", padx=4)
        option_menu2 = tk.OptionMenu(row1, self.play_mode, "顺序", "循环", "随机")
        option_menu2.config(
            bg="#3498DB",        # 背景色（淡蓝色）
            fg="white",          # 字体颜色
            activebackground="#48A2DE",
            activeforeground="white",
            highlightthickness=0,
            relief="flat"
        )
        option_menu2["menu"].config(
            bg="white",          # 下拉菜单背景
            fg="black"           # 下拉菜单文字颜色
        )
        option_menu2.pack(side="left", padx=4)
        ttk.Label(row1, text="输出设备：").pack(side="left", padx=4)
        option_menu3 = tk.OptionMenu(row1, self.output_device, *output_devs)
        option_menu3.config(
            bg="#3498DB",        # 背景色（淡蓝色）
            fg="white",          # 字体颜色
            activebackground="#48A2DE",
            activeforeground="white",
            highlightthickness=0,
            relief="flat"
        )
        option_menu3["menu"].config(
            bg="white",          # 下拉菜单背景
            fg="black"           # 下拉菜单文字颜色
        )
        option_menu3.pack(side="left", padx=4)

        # --- 行3：麦克风 + 音量 ---
        row2 = ttk.Frame(audio_frame)
        row2.pack(pady=4)
        ttk.Label(row2, text="麦克风：").pack(side="left", padx=4)
        option_menu4 = tk.OptionMenu(row2, self.mic_device, *input_devs)
        option_menu4.config(
            bg="#3498DB",        # 背景色（淡蓝色）
            fg="white",          # 字体颜色
            activebackground="#48A2DE",
            activeforeground="white",
            highlightthickness=0,
            relief="flat"
        )
        option_menu4["menu"].config(
            bg="white",          # 下拉菜单背景
            fg="black"           # 下拉菜单文字颜色
        )
        option_menu4.pack(side="left", padx=4)
        tk.Checkbutton(row2, text="启用麦克风", variable=self.mic_enabled,
                    font=("Microsoft YaHei", 10)).pack(side="left", padx=4)
        mic_frame = ttk.Frame(row2)
        mic_frame.pack(side="left", padx=4)

        ttk.Label(mic_frame, text="麦克风音量", font=("Microsoft YaHei", 10)).pack(anchor="w")
        ttkb.Scale(row2, from_=0, to=1, value=self.mic_volume.get(),
           command=lambda val: self.mic_volume.set(float(val)),
           length=140, variable=self.mic_volume,
           bootstyle="info").pack(side="left", padx=4)



        # —— 状态持久化 —— #
        self.device_choice.trace_add("write", lambda *_: self.persist_settings())
        self.play_mode.trace_add("write",  lambda *_: self.persist_settings())
        self.output_device.trace_add("write", lambda *_: self.on_output_device_change())
        self.mic_device.trace_add("write",   lambda *_: self.on_mic_device_change())
        self.mic_volume.trace_add("write",   lambda *_: self.change_mic_volume())
        self.mic_enabled.trace_add("write",  lambda *_: self.toggle_mic())
        self.vocal_volume.trace_add("write", lambda *_: self.change_volume(
            self.vocal_volume.get()))
        self.accomp_volume.trace_add("write", lambda *_: self.change_accomp_volume(
            self.accomp_volume.get()))
        self.theme_choice.trace_add("write",   lambda *_: self.persist_settings())
        self.language_choice.trace_add("write", lambda *_: self.persist_settings())

        # 播放控制按钮行
        ctrl_btn_row = ttk.Frame(ctrl_tab)
        ctrl_btn_row.grid(row=2, column=0, pady=(8, 4))
        self.prev_button = ttk.Button(ctrl_btn_row, text="⏮",
                                    command=self.play_previous_song,
                                    bootstyle="secondary", width=3)
        self.prev_button.pack(side=tk.LEFT, padx=5)

        self.pause_button = ttk.Button(ctrl_btn_row, text="⏯",
                                    command=self.toggle_pause, state=tk.DISABLED,
                                    bootstyle="warning", width=3)
        self.pause_button.pack(side=tk.LEFT, padx=5)

        self.next_button = ttk.Button(ctrl_btn_row, text="⏭",
                                    command=self.play_next_song_manual,
                                    bootstyle="secondary", width=3)
        self.next_button.pack(side=tk.LEFT, padx=5)

        # 人声音量滑块（使用 ttkb + 手动标签）
        self.vocal_frame = ttk.Frame(ctrl_tab)
        self.vocal_frame.grid(row=3, column=0, sticky="ew", padx=30)

        self.vocal_label = ttk.Label(self.vocal_frame,
                                    text=f"🎤 人声 {int(self.vocal_volume.get()*100)}%",
                                    font=("Microsoft YaHei", 11))
        self.vocal_label.pack(anchor="w")

        self.vol_slider = ttkb.Scale(self.vocal_frame, from_=0, to=1,
                                    command=self.change_volume,
                                    variable=self.vocal_volume,
                                    length=300, bootstyle="info")  # 蓝色滑块
        self.vol_slider.pack(fill="x")

        # 伴奏音量滑块
        self.accomp_frame = ttk.Frame(ctrl_tab)
        self.accomp_frame.grid(row=4, column=0, sticky="ew", padx=30)

        self.accomp_label = ttk.Label(self.accomp_frame,
                                    text=f"🎶 伴奏 {int(self.accomp_volume.get()*100)}%",
                                    font=("Microsoft YaHei", 11))
        self.accomp_label.pack(anchor="w")

        self.accomp_slider = ttkb.Scale(self.accomp_frame, from_=0, to=1,
                                        command=self.change_accomp_volume,
                                        variable=self.accomp_volume,
                                        length=300, bootstyle="info")
        self.accomp_slider.pack(fill="x")


        # 进度条 + 时间
        progress_row = ttk.Frame(ctrl_tab)
        progress_row.grid(row=5, column=0, sticky="ew", padx=30, pady=6)
        progress_row.columnconfigure(0, weight=1)

        ttk.Label(progress_row, text="播放进度").grid(row=0, column=0, sticky="w")

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttkb.Scale(progress_row, from_=0, to=100,
                                        orient=tk.HORIZONTAL,
                                        variable=self.progress_var,
                                        length=400,
                                        bootstyle="info")  # 蓝色风格
        self.progress_bar.grid(row=1, column=0, sticky="ew")
        self.progress_bar.bind("<ButtonPress-1>", self.start_drag)
        self.progress_bar.bind("<ButtonRelease-1>", self.on_seek)

        # 播放时间标签
        self.time_label = ttk.Label(ctrl_tab, text="00:00 / 00:00",
                                    font=("Courier", 12, "bold"))
        self.time_label.grid(row=6, column=0, sticky="e", padx=30)

        # 导出按钮
        export_row = ttk.Frame(ctrl_tab)
        export_row.grid(row=7, column=0, pady=4)
        ttk.Button(export_row, text="导出人声",  command=self.export_vocals,
                bootstyle="info").pack(side=tk.LEFT, padx=6)
        ttk.Button(export_row, text="导出伴奏",  command=self.export_accompaniment,
                bootstyle="info").pack(side=tk.LEFT, padx=6)

        # 待播列表（可折叠）
        queue_row = ttk.Frame(ctrl_tab)
        queue_row.grid(row=8, column=0, sticky="ew", padx=30, pady=6)
        queue_row.columnconfigure(0, weight=1)
        self.toggle_queue_button = ttk.Button(queue_row, text="显示待播列表",
                                            command=self.toggle_queue)
        self.toggle_queue_button.grid(row=0, column=0, sticky="w")

        self.queue_content = ttk.Frame(queue_row)
        self.queue_list_frame = ttk.Frame(self.queue_content)
        self.queue_list_frame.pack(fill="both", expand=True)
        self.clear_queue_btn = ttk.Button(self.queue_content, text="清空列表",
                                        command=self.clear_queue,
                                        bootstyle="danger-outline")
        self.clear_queue_btn.pack(pady=2)
        self.queue_visible = False
        self.update_queue_listbox()

        # ---------- 歌词页 ---------- #
        lyric_tab.columnconfigure(0, weight=1)
        lyric_tab.rowconfigure(0,    weight=1)
        self.lyrics_box = tk.Text(lyric_tab, font=("Microsoft YaHei", 14))
        self.lyrics_box.grid(row=0, column=0, sticky="nsew", pady=4)

        # =============== 启动时加载默认文件夹 =============== #
        if self.music_folder and os.path.isdir(self.music_folder):
            self.load_folder(self.music_folder)

        # =============== 其余运行控制变量 =============== #
        self.play_lock         = threading.Lock()  # 防止重复播放
        self.auto_next_enabled = True              # 控制是否启用自动播放下一首




    def choose_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.load_folder(folder)
            self.persist_settings()

    def load_folder(self, folder):
        self.music_folder = folder
        self.all_music_files = [os.path.join(folder, f) for f in os.listdir(folder)
                               if f.lower().endswith((".mp3", ".flac"))]
        self.all_music_files.sort()
        self.search_var.set("")
        self.music_files = list(self.all_music_files)
        self.refresh_file_listbox()
        self.update_queue_listbox()

    def refresh_file_listbox(self):
        self.file_listbox.delete(0, tk.END)
        for f in self.music_files:
            self.file_listbox.insert(tk.END, os.path.basename(f))

    def update_queue_listbox(self):
        for child in self.queue_list_frame.winfo_children():
            child.destroy()
        if not self.future_queue:
            ttk.Label(self.queue_list_frame, text="(空)",
                     font=("Microsoft YaHei", 10)).pack()
        else:
            for idx, p in enumerate(self.future_queue):
                row = ttk.Frame(self.queue_list_frame)
                row.pack(fill="x")
                ttk.Label(row, text=os.path.basename(p), font=("Microsoft YaHei", 10))\
                    .pack(side=tk.LEFT, fill="x", expand=True)
                ttk.Button(row, text="删除",
                           command=lambda i=idx: self.remove_from_queue(i),
                           bootstyle="danger").pack(side=tk.RIGHT)

    def clear_queue(self):
        if self.future_queue:
            self.future_queue.clear()
            self.update_queue_listbox()
            self.persist_settings()

    def remove_from_queue(self, index):
        if 0 <= index < len(self.future_queue):
            removed = self.future_queue.pop(index)
            self.lyrics_box.insert("end", f"❌ 已移除：{os.path.basename(removed)}\n")
            self.update_queue_listbox()
            self.persist_settings()

    def toggle_queue(self):
        if self.queue_visible:
            self.queue_content.grid_remove()
            self.queue_visible = False
            self.toggle_queue_button.config(text="显示待播列表")
        else:
            self.queue_content.grid(row=1, column=0, sticky="ew", pady=2)
            self.queue_visible = True
            self.toggle_queue_button.config(text="隐藏待播列表")


    def search_songs(self):
        query = self.search_var.get().lower()
        if not query:
            self.music_files = list(self.all_music_files)
        else:
            self.music_files = [f for f in self.all_music_files if query in os.path.basename(f).lower()]
        self.refresh_file_listbox()

    def on_song_double_click(self, event):
        index = self.file_listbox.curselection()
        if not index:
            return
        self.auto_next_enabled = False  # 禁止自动续播
        if self.player:
            self.player.stop()
            self.player = None
        self.current_index = index[0]
        threading.Thread(target=lambda: self.play_song(self.current_index), daemon=True).start()

    def add_to_queue(self):
        index = self.file_listbox.curselection()
        if not index:
            return
        path = self.music_files[index[0]]
        # Store in arrival order and play in FIFO by popping from the front
        self.future_queue.append(path)
        self.lyrics_box.insert("end", f"✅ 已加入待播：{os.path.basename(path)}\n")
        self.update_queue_listbox()
        self.persist_settings()


    def play_previous_song(self):
        if not self.music_files:
            return
        if self.play_history:
            entry = self.play_history.pop()
            path = entry["path"] if isinstance(entry, dict) else entry
            if path in self.music_files:
                prev_index = self.music_files.index(path)
                if self.player:
                    self.player.stop()
                    self.player = None
                self.current_index = prev_index
                if self.prev_audio_data and self.prev_audio_data[0] == prev_index:
                    _, vocals, accomp, sr = self.prev_audio_data
                    threading.Thread(
                        target=lambda: self.play_song(prev_index, (vocals, accomp, sr), update_history=False, resume=False, keep_current_as_next=True),
                        daemon=True
                    ).start()
                else:
                    threading.Thread(target=lambda: self.play_song(prev_index, update_history=False, resume=False, keep_current_as_next=True), daemon=True).start()
                return
        prev_index = self.get_prev_index()
        if prev_index is None:
            return
        if self.player:
            self.player.stop()
            self.player = None
        self.current_index = prev_index
        if self.prev_audio_data and self.prev_audio_data[0] == prev_index:
            _, vocals, accomp, sr = self.prev_audio_data
            threading.Thread(
                target=lambda: self.play_song(prev_index, (vocals, accomp, sr), update_history=False, resume=False, keep_current_as_next=True),
                daemon=True
            ).start()
        else:
            threading.Thread(target=lambda: self.play_song(prev_index, update_history=False, resume=False, keep_current_as_next=True), daemon=True).start()

    def play_next_song_manual(self):
        self.auto_next_enabled = False  # 禁止自动续播
        # When skipping manually, use queue if available, otherwise follow play mode
        next_index = self.get_next_index()
        if next_index is not None:
            if self.player:
                self.player.stop()
                self.player = None
            self.current_index = next_index
            if self.next_audio_data and self.next_audio_data[0] == next_index:
                _, vocals, accomp, sr = self.next_audio_data
                threading.Thread(
                    target=lambda: self.play_song(next_index, (vocals, accomp, sr), resume=False),
                    daemon=True
                ).start()
            else:
                threading.Thread(target=lambda: self.play_song(next_index, resume=False), daemon=True).start()


    def play_song(self, index, preloaded=None, update_history=True, resume=True, keep_current_as_next=False):
        if not self.play_lock.acquire(blocking=False):
            return  # 正在播放时不重复执行

        try:
            self.auto_next_enabled = True  # 默认启用自动续播
            self.session_id = str(uuid.uuid4())
            current_session = self.session_id
            self.next_audio_data = None
            old_data = self.current_audio_data
            if update_history and self.audio_path:
                self.play_history.append({"path": self.audio_path, "time": time.time()})
                if len(self.play_history) > self.history_limit:
                    self.play_history = self.play_history[-self.history_limit:]
            if self.player:
                self.player.stop()
                self.player = None
            if old_data:
                if keep_current_as_next:
                    self.next_audio_data = old_data
                self.prev_audio_data = old_data
            self.current_audio_data = None
            self.current_index = index

            self.audio_path = self.music_files[index]
            song_name = os.path.basename(self.audio_path)
            self.current_file_label.config(text=f"当前播放：{song_name}")
            self.lyrics_box.delete("1.0", "end")
            self.pause_button.config(state=tk.NORMAL)

            if preloaded:
                vocals, accomp, sr = preloaded
                self.lyrics_box.insert("end", "✅ 使用缓存播放\n")
            else:
                self.lyrics_box.insert("end", "🎶 正在分离人声...\n")
                self.show_toast("正在分离中...")
                device = self.device_choice.get()
                vocals, accomp, sr = separate_audio_in_memory(self.audio_path, device=device)
                if self.session_id != current_session:
                    return
                self.lyrics_box.insert("end", "✅ 分离完成，开始播放\n")
                self.show_toast("分离完成")

            mic_dev = None if not self.mic_enabled.get() else self.get_selected_mic_index()
            out_dev = self.get_selected_output_index()
            try:
                dev_info = sd.query_devices(out_dev, 'output') if out_dev is not None else sd.query_devices(None, 'output')
                target_sr = int(dev_info.get('default_samplerate', sr)) or sr
                if target_sr <= 0 or target_sr > 192000:
                    target_sr = sr
            except Exception:
                target_sr = sr
            if sr != target_sr:
                vocals = resample_audio(vocals, sr, target_sr)
                accomp = resample_audio(accomp, sr, target_sr)
                sr = target_sr
            self.player = AudioPlayer(vocals, accomp, sr, output_device=out_dev, mic_device=mic_dev, mic_enabled=self.mic_enabled.get(), latency=0.03)
            self.player.set_mic_volume(self.mic_volume.get())
            self.player.set_vocal_volume(self.vocal_volume.get())
            self.player.set_accomp_volume(self.accomp_volume.get())
            try:
                self.player.play()
            except Exception as e:
                messagebox.showerror("音频设备错误", str(e))
                self.player.stop()
                self.player = None
                return
            if self.player.output_device is None and out_dev is not None:
                self.output_device.set("默认")
                self.persist_settings()
            if resume:
                if self.audio_path in self.progress_map:
                    self.player.seek_to(self.progress_map[self.audio_path])
            else:
                self.progress_map[self.audio_path] = 0

            self.current_audio_data = (index, vocals, accomp, sr)

            lrc_path = os.path.splitext(self.audio_path)[0] + ".lrc"
            try:
                lyrics = parse_lrc(lrc_path)
                start_lyrics_display(lyrics, self.player, self.lyrics_box)
            except FileNotFoundError:
                self.lyrics_box.insert("end", "⚠️ 未找到歌词文件\n")

            self.progress_bar.config(state=tk.NORMAL)
            if resume:
                progress = self.progress_map.get(self.audio_path, 0)
            else:
                progress = 0
            self.progress_var.set(progress * 100)
            if not self.update_loop_running:
                threading.Thread(target=self.update_progress_loop, daemon=True).start()

            threading.Thread(target=lambda: self.preload_next_song(current_session), daemon=True).start()
            threading.Thread(target=lambda: self.preload_prev_song(current_session), daemon=True).start()
            threading.Thread(target=lambda: self.monitor_and_play_next(current_session), daemon=True).start()

        except Exception as e:
            messagebox.showerror("出错", str(e))
        finally:
            self.play_lock.release()
            self.persist_settings()



    def preload_next_song(self, session_id):
        next_index = self.get_next_index(peek=True)
        if next_index is None or session_id != self.session_id:
            return
        # 如果上一首就是接下来的歌曲，直接复用缓存
        if self.prev_audio_data and self.prev_audio_data[0] == next_index:
            self.next_audio_data = self.prev_audio_data
            return
        if self.next_audio_data and self.next_audio_data[0] == next_index:
            return
        next_path = self.music_files[next_index]
        try:
            device = self.device_choice.get()
            vocals, accomp, sr = separate_audio_in_memory(next_path, device=device)
            if session_id == self.session_id:
                self.next_audio_data = (next_index, vocals, accomp, sr)
        except:
            self.next_audio_data = None

    def preload_prev_song(self, session_id):
        prev_index = self.get_prev_index()
        if prev_index is None or session_id != self.session_id:
            return
        if self.prev_audio_data and self.prev_audio_data[0] == prev_index:
            return
        if self.next_audio_data and self.next_audio_data[0] == prev_index:
            self.prev_audio_data = self.next_audio_data
            return
        prev_path = self.music_files[prev_index]
        try:
            device = self.device_choice.get()
            vocals, accomp, sr = separate_audio_in_memory(prev_path, device=device)
            if session_id == self.session_id:
                self.prev_audio_data = (prev_index, vocals, accomp, sr)
        except:
            self.prev_audio_data = None

    def monitor_and_play_next(self, session_id):
        while self.player and self.player.playing and session_id == self.session_id:
            time.sleep(0.5)
        if session_id != self.session_id:
            return
        if not self.auto_next_enabled:
            return  # 用户手动切歌，取消自动续播

        if self.next_audio_data:
            index, vocals, accomp, sr = self.next_audio_data
            if self.current_audio_data:
                self.prev_audio_data = self.current_audio_data
                if self.audio_path:
                    self.play_history.append({"path": self.audio_path, "time": time.time()})
                    if len(self.play_history) > self.history_limit:
                        self.play_history = self.play_history[-self.history_limit:]
            self.current_index = index
            self.audio_path = self.music_files[index]
            self.current_file_label.config(text=f"当前播放：{os.path.basename(self.audio_path)}")
            self.lyrics_box.delete("1.0", "end")
            self.lyrics_box.insert("end", "✅ 自动播放下一首\n")

            if self.player:
                self.player.stop()

            mic_dev = None if not self.mic_enabled.get() else self.get_selected_mic_index()
            out_dev = self.get_selected_output_index()
            try:
                dev_info = sd.query_devices(out_dev, 'output') if out_dev is not None else sd.query_devices(None, 'output')
                target_sr = int(dev_info.get('default_samplerate', sr)) or sr
                if target_sr <= 0 or target_sr > 192000:
                    target_sr = sr
            except Exception:
                target_sr = sr
            if sr != target_sr:
                vocals = resample_audio(vocals, sr, target_sr)
                accomp = resample_audio(accomp, sr, target_sr)
                sr = target_sr
            self.player = AudioPlayer(vocals, accomp, sr, output_device=out_dev, mic_device=mic_dev, mic_enabled=self.mic_enabled.get(), latency=0.03)
            self.player.set_mic_volume(self.mic_volume.get())
            self.player.set_vocal_volume(self.vocal_volume.get())
            self.player.set_accomp_volume(self.accomp_volume.get())
            try:
                self.player.play()
            except Exception as e:
                messagebox.showerror("音频设备错误", str(e))
                self.player.stop()
                self.player = None
                return
            if self.player.output_device is None and out_dev is not None:
                self.output_device.set("默认")
                self.persist_settings()
            self.current_audio_data = (index, vocals, accomp, sr)

            lrc_path = os.path.splitext(self.audio_path)[0] + ".lrc"
            try:
                lyrics = parse_lrc(lrc_path)
                start_lyrics_display(lyrics, self.player, self.lyrics_box)
            except:
                self.lyrics_box.insert("end", "⚠️ 无歌词\n")

            self.progress_bar.config(state=tk.NORMAL)
            self.progress_var.set(self.progress_map.get(self.audio_path, 0) * 100)
            if not self.update_loop_running:
                threading.Thread(target=self.update_progress_loop, daemon=True).start()

            threading.Thread(target=lambda: self.preload_next_song(self.session_id), daemon=True).start()
            threading.Thread(target=lambda: self.preload_prev_song(self.session_id), daemon=True).start()


    def get_next_index(self, peek=False, queue_only=False):
        if not self.music_files:
            return None
        if self.future_queue:
            path = self.future_queue[0] if peek else self.future_queue.pop(0)
            if not peek:
                self.update_queue_listbox()
                self.persist_settings()
            if path in self.music_files:
                return self.music_files.index(path)
        if queue_only:
            return None
        mode = self.play_mode.get()
        if mode == "顺序":
            return self.current_index + 1 if self.current_index + 1 < len(self.music_files) else None
        elif mode == "循环":
            return (self.current_index + 1) % len(self.music_files)
        elif mode == "随机":
            if self.next_audio_data:
                return self.next_audio_data[0]
            candidates = list(range(len(self.music_files)))
            if len(candidates) > 1:
                candidates.remove(self.current_index)
            return random.choice(candidates)
        return None

    def get_prev_index(self):
        if not self.music_files:
            return None
        mode = self.play_mode.get()
        if mode == "顺序":
            return self.current_index - 1 if self.current_index > 0 else None
        elif mode == "循环":
            return (self.current_index - 1) % len(self.music_files)
        elif mode == "随机":
            if self.prev_audio_data:
                return self.prev_audio_data[0]
            return None
        return None

    def toggle_pause(self):
        if self.player:
            if self.player.paused:
                self.player.resume()
                self.pause_button.config(text="⏸ 暂停")
            else:
                self.player.pause()
                self.pause_button.config(text="▶ 继续")

    def seek_relative(self, seconds):
        if self.player:
            total = self.player.num_frames / self.player.sample_rate
            new_time = self.player.get_current_time() + seconds
            new_time = max(0.0, min(new_time, total))
            self.player.seek_to(new_time / total)
            self.progress_var.set((new_time / total) * 100)

    def adjust_volume(self, delta):
        v = min(1.0, max(0.0, self.vocal_volume.get() + delta))
        a = min(1.0, max(0.0, self.accomp_volume.get() + delta))
        self.vocal_volume.set(v)
        self.accomp_volume.set(a)

    def show_toast(self, message):
        try:
            from ttkbootstrap.toast import ToastNotification
            toast = ToastNotification(title="提示", message=message, duration=2000, bootstyle="info")
            toast.show_toast()
        except Exception:
            messagebox.showinfo("提示", message)

    def change_volume(self, val):
        if self.player:
            self.player.set_vocal_volume(float(val))
        # 实时更新标签
        if hasattr(self, "vocal_label"):
            self.vocal_label.config(text=f"🎤 人声 {int(float(val)*100)}%")
        self.persist_settings()

    def change_accomp_volume(self, val):
        if self.player:
            self.player.set_accomp_volume(float(val))
        # 实时更新标签
        if hasattr(self, "accomp_label"):
            self.accomp_label.config(text=f"🎶 伴奏 {int(float(val)*100)}%")
        self.persist_settings()

    def change_mic_volume(self, *args):
        if self.player:
            self.player.set_mic_volume(float(self.mic_volume.get()))
        self.persist_settings()

    def on_mic_device_change(self, *args):
        self.persist_settings()
        if self.player and self.mic_enabled.get():
            mic_dev = self.get_selected_mic_index()
            try:
                self.player.set_mic_enabled(True, mic_dev)
                self.show_toast("已切换麦克风")
            except Exception as e:
                messagebox.showerror("麦克风错误", str(e))
                self.mic_enabled.set(False)

    def toggle_mic(self, *args):
        self.persist_settings()
        if self.player:
            if self.mic_enabled.get():
                mic_dev = self.get_selected_mic_index()
                try:
                    self.player.set_mic_enabled(True, mic_dev)
                    self.player.set_mic_volume(float(self.mic_volume.get()))
                except Exception as e:
                    messagebox.showerror("麦克风错误", str(e))
                    self.mic_enabled.set(False)
            else:
                self.player.set_mic_enabled(False)

    def on_output_device_change(self, *args):
        self.persist_settings()
        if self.player:
            out_dev = self.get_selected_output_index()
            try:
                self.player.change_output_device(out_dev)
                self.show_toast("已切换输出设备")
            except Exception as e:
                messagebox.showerror("输出设备错误", str(e))

    def start_drag(self, event):
        self.dragging = True

    def update_progress_loop(self):
        self.update_loop_running = True
        while self.player and (self.player.playing or self.player.paused):
            current = self.player.get_current_time()
            total = self.player.num_frames / self.player.sample_rate
            if not self.dragging:
                self.progress_var.set(self.player.get_progress() * 100)
            self.time_label.config(text=f"{self.format_time(current)} / {self.format_time(total)}")
            if self.audio_path:
                self.progress_map[self.audio_path] = self.player.get_progress()
            time.sleep(0.2)
        self.update_loop_running = False

    def on_seek(self, event):
        if self.player:
            percent = self.progress_var.get() / 100
            self.player.seek_to(percent)
            if self.audio_path:
                self.progress_map[self.audio_path] = percent
        self.dragging = False

    def format_time(self, seconds):
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    def export_vocals(self):
        if not self.current_audio_data:
            messagebox.showwarning("未播放", "请先播放歌曲再导出")
            return
        _, vocals, _, sr = self.current_audio_data
        base = os.path.splitext(os.path.basename(self.audio_path))[0]
        default_name = f"{base} - 人声.wav"
        path = filedialog.asksaveasfilename(defaultextension=".wav",
                                            filetypes=[("WAV 文件", "*.wav")],
                                            initialfile=default_name)
        if not path:
            return
        threading.Thread(target=self.save_audio_file, args=(path, vocals, sr),
                         daemon=True).start()

    def export_accompaniment(self):
        if not self.current_audio_data:
            messagebox.showwarning("未播放", "请先播放歌曲再导出")
            return
        _, _, accomp, sr = self.current_audio_data
        base = os.path.splitext(os.path.basename(self.audio_path))[0]
        default_name = f"{base} - 伴奏.wav"
        path = filedialog.asksaveasfilename(defaultextension=".wav",
                                            filetypes=[("WAV 文件", "*.wav")],
                                            initialfile=default_name)
        if not path:
            return
        threading.Thread(target=self.save_audio_file, args=(path, accomp, sr),
                         daemon=True).start()

    def save_audio_file(self, path, data, sr):
        error = None
        try:
            tensor = torch.from_numpy(data.T)
            torchaudio.save(path, tensor, sr)
        except Exception as e:
            error = e
            if sf is not None:
                try:
                    sf.write(path, data, sr)
                    error = None
                except Exception as e2:
                    error = e2
        if error is None:
            self.lyrics_box.insert("end", f"✅ 已导出：{os.path.basename(path)}\n")
        else:
            messagebox.showerror("导出错误", str(error))

    def get_selected_mic_index(self):
        """Return the valid sounddevice index for the selected microphone.

        If the stored device index no longer exists, reset to the default
        "无" option and return ``None``.
        """
        idx = self.input_device_map.get(self.mic_device.get())
        if idx is not None:
            try:
                sd.query_devices(idx, "input")
            except Exception:
                self.mic_device.set("无")
                self.persist_settings()
                idx = None
        return idx

    def get_selected_output_index(self):
        """Return the valid sounddevice index for the selected output device.

        If the stored device index no longer exists, reset to the default
        "默认" option and return ``None``.
        """
        idx = self.output_device_map.get(self.output_device.get())
        if idx is not None:
            try:
                sd.query_devices(idx, "output")
            except Exception:
                self.output_device.set("默认")
                self.persist_settings()
                idx = None
        return idx

    def persist_settings(self):
        settings = {
            "device": self.device_choice.get(),
            "play_mode": self.play_mode.get(),
            "music_folder": self.music_folder,
            "output_device": self.output_device.get(),
            "mic_device": self.mic_device.get(),
            "mic_volume": self.mic_volume.get(),
            "mic_enabled": self.mic_enabled.get(),
            "vocal_volume": self.vocal_volume.get(),
            "accomp_volume": self.accomp_volume.get(),
            "queue": self.future_queue,
            "history": self.play_history,
            "theme": self.theme_choice.get(),
            "language": self.language_choice.get(),
            "progress": self.progress_map,
        }
        save_settings(settings)

    def on_close(self):
        if self.player and self.audio_path:
            self.progress_map[self.audio_path] = self.player.get_progress()
        self.persist_settings()
        if self.player:
            self.player.stop()
        self.root.destroy()


    
