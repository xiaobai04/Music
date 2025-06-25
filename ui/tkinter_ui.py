"""Tkinter user interface for the Demucs based music player."""

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

from utils.settings import load_settings

from .mixins.playlist_mixin import PlaylistMixin
from .mixins.playback_mixin import PlaybackMixin
from .mixins.utils_mixin import UtilsMixin
from .mixins.control_mixin import ControlMixin
from .mixins.progress_mixin import ProgressMixin
from .mixins.lyrics_mixin import LyricsMixin
from .mixins.search_mixin import SearchMixin


class PlayerApp(
    PlaylistMixin,
    PlaybackMixin,
    ControlMixin,
    ProgressMixin,
    LyricsMixin,
    SearchMixin,
    UtilsMixin,
):
    """Main application window composed of multiple mixins."""

    def __init__(self, root):
        """Construct all widgets and initialize state."""
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
        self.lyrics_font_size = tk.IntVar(value=settings.get("lyric_font_size", 14))
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
        self.lyrics_box = tk.Text(lyric_tab, font=("Microsoft YaHei", self.lyrics_font_size.get()))
        self.lyrics_box.grid(row=0, column=0, sticky="nsew", pady=4)

        lyric_progress = ttk.Frame(lyric_tab)
        lyric_progress.grid(row=1, column=0, sticky="ew", padx=30, pady=6)
        lyric_progress.columnconfigure(0, weight=1)
        ttk.Label(lyric_progress, text="播放进度").grid(row=0, column=0, sticky="w")
        self.progress_bar_lyrics = ttkb.Scale(lyric_progress, from_=0, to=100,
                                              orient=tk.HORIZONTAL,
                                              variable=self.progress_var,
                                              length=400, bootstyle="info")
        self.progress_bar_lyrics.grid(row=1, column=0, sticky="ew")
        self.progress_bar_lyrics.bind("<ButtonPress-1>", self.start_drag)
        self.progress_bar_lyrics.bind("<ButtonRelease-1>", self.on_seek)

        self.time_label_lyrics = ttk.Label(lyric_tab, text="00:00 / 00:00",
                                           font=("Courier", 12, "bold"))
        self.time_label_lyrics.grid(row=2, column=0, sticky="e", padx=30)

        lyric_ctrl_row = ttk.Frame(lyric_tab)
        lyric_ctrl_row.grid(row=3, column=0, pady=(8, 4))
        self.prev_button_lyrics = ttk.Button(lyric_ctrl_row, text="⏮",
                                            command=self.play_previous_song,
                                            bootstyle="secondary", width=3)
        self.prev_button_lyrics.pack(side=tk.LEFT, padx=5)
        self.pause_button_lyrics = ttk.Button(lyric_ctrl_row, text="⏯",
                                             command=self.toggle_pause,
                                             state=tk.DISABLED,
                                             bootstyle="warning", width=3)
        self.pause_button_lyrics.pack(side=tk.LEFT, padx=5)
        self.next_button_lyrics = ttk.Button(lyric_ctrl_row, text="⏭",
                                            command=self.play_next_song_manual,
                                            bootstyle="secondary", width=3)
        self.next_button_lyrics.pack(side=tk.LEFT, padx=5)

        font_row = ttk.Frame(lyric_tab)
        font_row.grid(row=4, column=0, pady=(6, 2))
        ttk.Button(font_row, text="A-", command=self.decrease_font_size,
                   width=3).pack(side=tk.LEFT, padx=2)
        ttk.Button(font_row, text="A+", command=self.increase_font_size,
                   width=3).pack(side=tk.LEFT, padx=2)

        # =============== 启动时加载默认文件夹 =============== #
        if self.music_folder and os.path.isdir(self.music_folder):
            self.load_folder(self.music_folder)

        # =============== 其余运行控制变量 =============== #
        self.play_lock         = threading.Lock()  # 防止重复播放
        self.auto_next_enabled = True              # 控制是否启用自动播放下一首




