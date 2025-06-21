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
        self.root = root
        self.root.title("🎵 人声分离播放器")
        self.root.geometry("1200x720")

        # Use a modern ttk theme provided by ttkbootstrap
        style = ttkb.Style()
        self.style = style

        settings = load_settings()

        self.theme_choice = tk.StringVar(value=settings.get("theme", "flatly"))
        self.style.theme_use(self.theme_choice.get())
        self.theme_choice.trace_add("write", lambda *a: self.style.theme_use(self.theme_choice.get()))
        self.language_choice = tk.StringVar(value=settings.get("language", "中文"))
        self.progress_map = dict(settings.get("progress", {}))

        # Prefer low-latency devices when available
        sd.default.latency = "low"

        # On Windows prefer the WASAPI host for better compatibility
        if platform.system() == "Windows":
            for idx, api in enumerate(sd.query_hostapis()):
                if "WASAPI" in api.get("name", ""):
                    try:
                        sd.default.hostapi = idx
                    except AttributeError:
                        # `sd.default.hostapi` became read-only in
                        # newer versions of sounddevice.  Setting the
                        # default device still ensures the WASAPI host
                        # is used where possible.
                        pass
                    in_dev = api.get("default_input_device", -1)
                    out_dev = api.get("default_output_device", -1)
                    cur_in, cur_out = sd.default.device
                    if in_dev >= 0:
                        cur_in = in_dev
                    if out_dev >= 0:
                        cur_out = out_dev
                    sd.default.device = (cur_in, cur_out)
                    break

        self.audio_path = None
        self.player = None
        self.device_choice = tk.StringVar(value=settings.get("device", "cuda"))
        self.play_mode = tk.StringVar(value=settings.get("play_mode", "顺序"))
        self.music_folder = settings.get("music_folder", "")
        self.output_device = tk.StringVar(value=settings.get("output_device", "默认"))
        self.output_device_map = {}
        self.mic_device = tk.StringVar(value=settings.get("mic_device", "无"))
        self.input_device_map = {}
        self.mic_volume = tk.DoubleVar(value=settings.get("mic_volume", 1.0))
        self.vocal_volume = tk.DoubleVar(value=settings.get("vocal_volume", 1.0))
        self.accomp_volume = tk.DoubleVar(value=settings.get("accomp_volume", 1.0))
        self.mic_enabled = tk.BooleanVar(value=settings.get("mic_enabled", False))
        self.update_loop_running = False
        self.dragging = False
        self.music_files = []
        self.all_music_files = []
        self.current_index = -1
        self.next_audio_data = None
        self.prev_audio_data = None
        self.current_audio_data = None
        self.future_queue = list(settings.get("queue", []))
        self.session_id = None

        menu = tk.Menu(root)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="选择音乐文件夹", command=self.choose_folder)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.on_close)
        menu.add_cascade(label="文件", menu=file_menu)

        theme_menu = tk.Menu(menu, tearoff=0)
        theme_menu.add_radiobutton(label="浅色", variable=self.theme_choice, value="flatly")
        theme_menu.add_radiobutton(label="暗色", variable=self.theme_choice, value="darkly")
        menu.add_cascade(label="外观", menu=theme_menu)

        lang_menu = tk.Menu(menu, tearoff=0)
        lang_menu.add_radiobutton(label="中文", variable=self.language_choice, value="中文")
        lang_menu.add_radiobutton(label="English", variable=self.language_choice, value="English")
        menu.add_cascade(label="语言", menu=lang_menu)

        root.config(menu=menu)

        # Global key bindings
        root.bind('<space>', lambda e: self.toggle_pause())
        root.bind('<Left>', lambda e: self.seek_relative(-5))
        root.bind('<Right>', lambda e: self.seek_relative(5))
        root.bind('<Up>', lambda e: self.adjust_volume(0.05))
        root.bind('<Down>', lambda e: self.adjust_volume(-0.05))

        paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        left_frame = ttk.Frame(paned)
        right_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)
        paned.add(right_frame, weight=3)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 左侧文件列表
        left_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Button(left_frame, text="选择音乐文件夹", command=self.choose_folder,
                   bootstyle="primary-outline").pack(pady=5)

        search_frame = ttk.Frame(left_frame)
        search_frame.pack(pady=5, fill="x")
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(search_frame, textvariable=self.search_var,
                                     font=("Microsoft YaHei", 11))
        self.search_entry.pack(side=tk.LEFT, fill="x", expand=True)
        self.search_entry.bind("<Return>", lambda e: self.search_songs())
        ttk.Button(search_frame, text="搜索", command=self.search_songs,
                   bootstyle="secondary").pack(side=tk.LEFT, padx=5)

        self.file_listbox = tk.Listbox(left_frame, font=("Microsoft YaHei", 11))
        self.file_listbox.pack(fill="both", expand=True)
        self.file_listbox.bind("<Double-Button-1>", self.on_song_double_click)

        ttk.Button(left_frame, text="加入播放列表", command=self.add_to_queue,
                   bootstyle="success").pack(pady=5)

        # 右侧控制面板
        right_frame.pack(fill="both", expand=True, padx=10, pady=10)

        notebook = ttk.Notebook(right_frame)
        ctrl_tab = ttk.Frame(notebook)
        lyric_tab = ttk.Frame(notebook)
        notebook.add(ctrl_tab, text="控制")
        notebook.add(lyric_tab, text="歌词")
        notebook.pack(fill="both", expand=True)

        self.current_file_label = ttk.Label(ctrl_tab, text="当前播放：", font=("Microsoft YaHei", 12, "bold"))
        self.current_file_label.pack(pady=5)

        row1 = ttk.Frame(ctrl_tab)
        row1.pack()
        ttk.Label(row1, text="分离方式：").pack(side=tk.LEFT)
        tk.OptionMenu(row1, self.device_choice, "cpu", "cuda").pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="播放模式：").pack(side=tk.LEFT, padx=(20, 0))
        tk.OptionMenu(row1, self.play_mode, "顺序", "循环", "随机").pack(side=tk.LEFT)

        # 设备列表
        all_devices = list(enumerate(sd.query_devices()))
        hostapis = sd.query_hostapis()

        # 输出设备
        row2 = ttk.Frame(ctrl_tab)
        row2.pack()
        output_devs = []
        self.output_device_map.clear()
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
        ttk.Label(row2, text="输出设备：").pack(side=tk.LEFT)
        tk.OptionMenu(row2, self.output_device, *output_devs).pack(side=tk.LEFT, padx=5)

        # 麦克风设备选择，显示索引和 Host API，避免名称重复
        devices = [(i, d) for i, d in all_devices if d['max_input_channels'] > 0]
        input_devs = []
        self.input_device_map.clear()
        for i, dev in devices:
            label = f"{i}: {dev['name']} ({hostapis[dev['hostapi']]['name']})"
            input_devs.append(label)
            self.input_device_map[label] = i
        if not input_devs:
            input_devs = ["无"]
            self.input_device_map["无"] = None
        if self.mic_device.get() not in input_devs:
            self.mic_device.set("无")
        row3 = ttk.Frame(ctrl_tab)
        row3.pack()
        ttk.Label(row3, text="麦克风：").pack(side=tk.LEFT)
        tk.OptionMenu(row3, self.mic_device, *input_devs).pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(row3, text="启用麦克风", variable=self.mic_enabled,
                       font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=5)
        tk.Scale(row3, from_=0, to=1, resolution=0.01, orient=tk.HORIZONTAL,
                 variable=self.mic_volume, label="麦克风音量", length=120,
                 font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=5)

        # 当选项变化时保存设置
        self.device_choice.trace_add("write", lambda *args: self.persist_settings())
        self.play_mode.trace_add("write", lambda *args: self.persist_settings())
        self.output_device.trace_add("write", lambda *args: self.on_output_device_change())
        self.mic_device.trace_add("write", lambda *args: self.on_mic_device_change())
        self.mic_volume.trace_add("write", lambda *args: self.change_mic_volume())
        self.mic_enabled.trace_add("write", lambda *args: self.toggle_mic())
        self.vocal_volume.trace_add("write", lambda *args: self.change_volume(self.vocal_volume.get()))
        self.accomp_volume.trace_add("write", lambda *args: self.change_accomp_volume(self.accomp_volume.get()))
        self.theme_choice.trace_add("write", lambda *args: self.persist_settings())
        self.language_choice.trace_add("write", lambda *args: self.persist_settings())

        control_frame = ttk.Frame(ctrl_tab)
        control_frame.pack(pady=5)

        self.prev_button = ttk.Button(control_frame, text="⏮ 上一首",
                                      command=self.play_previous_song,
                                      bootstyle="secondary")
        self.prev_button.pack(side=tk.LEFT, padx=5)

        self.pause_button = ttk.Button(control_frame, text="⏸ 暂停",
                                        command=self.toggle_pause,
                                        state=tk.DISABLED,
                                        bootstyle="warning")
        self.pause_button.pack(side=tk.LEFT, padx=5)

        self.next_button = ttk.Button(control_frame, text="⏭ 下一首",
                                      command=self.play_next_song_manual,
                                      bootstyle="secondary")
        self.next_button.pack(side=tk.LEFT, padx=5)

        self.vol_slider = tk.Scale(ctrl_tab, from_=0, to=1, resolution=0.01,
                                   orient=tk.HORIZONTAL, label="人声音量",
                                   command=self.change_volume,
                                   variable=self.vocal_volume,
                                   font=("Microsoft YaHei", 11))
        self.vol_slider.pack(fill="x", padx=30)

        self.accomp_slider = tk.Scale(ctrl_tab, from_=0, to=1, resolution=0.01,
                                      orient=tk.HORIZONTAL, label="伴奏音量",
                                      command=self.change_accomp_volume,
                                      variable=self.accomp_volume,
                                      font=("Microsoft YaHei", 11))
        self.accomp_slider.pack(fill="x", padx=30)

        self.progress_var = tk.DoubleVar()
        progress_frame = ttk.Frame(ctrl_tab)
        progress_frame.pack(fill="x", padx=30, pady=10)
        ttk.Label(progress_frame, text="播放进度").pack(anchor="w")
        self.progress_bar = ttk.Scale(progress_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                      variable=self.progress_var)
        self.progress_bar.pack(fill="x", expand=True)
        self.progress_bar.bind("<ButtonPress-1>", self.start_drag)
        self.progress_bar.bind("<ButtonRelease-1>", self.on_seek)

        self.time_label = ttk.Label(ctrl_tab, text="00:00 / 00:00", font=("Courier", 12, "bold"))
        self.time_label.pack()

        export_frame = ttk.Frame(ctrl_tab)
        export_frame.pack(pady=5)
        ttk.Button(export_frame, text="导出人声", command=self.export_vocals,
                   bootstyle="info").pack(side=tk.LEFT, padx=5)
        ttk.Button(export_frame, text="导出伴奏", command=self.export_accompaniment,
                   bootstyle="info").pack(side=tk.LEFT, padx=5)

        queue_frame = ttk.Frame(ctrl_tab)
        queue_frame.pack(fill="x", padx=30, pady=5)
        self.toggle_queue_button = ttk.Button(queue_frame, text="显示待播列表", command=self.toggle_queue)
        self.toggle_queue_button.pack(anchor="w")
        self.queue_content = ttk.Frame(queue_frame)
        self.queue_list_frame = ttk.Frame(self.queue_content)
        self.queue_list_frame.pack(fill="both", expand=True)
        self.clear_queue_btn = ttk.Button(self.queue_content, text="清空列表", command=self.clear_queue,
                                         bootstyle="danger-outline")
        self.clear_queue_btn.pack(pady=2)
        self.queue_visible = False
        self.update_queue_listbox()

        if self.music_folder and os.path.isdir(self.music_folder):
            self.load_folder(self.music_folder)

        self.lyrics_box = tk.Text(lyric_tab, font=("Microsoft YaHei", 14))
        self.lyrics_box.pack(fill="both", expand=True, pady=5)

        self.play_lock = threading.Lock()  # 防止重复播放
        self.auto_next_enabled = True      # 控制是否启用自动播放下一首



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
            self.queue_content.pack_forget()
            self.queue_visible = False
            self.toggle_queue_button.config(text="显示待播列表")
        else:
            self.queue_content.pack(fill="x", pady=2)
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
        self.clear_queue()
        self.auto_next_enabled = False  # 禁止自动续播
        self.current_index = index[0]
        threading.Thread(target=lambda: self.play_song(self.current_index), daemon=True).start()

    def add_to_queue(self):
        index = self.file_listbox.curselection()
        if not index:
            return
        path = self.music_files[index[0]]
        self.future_queue.append(path)
        self.lyrics_box.insert("end", f"✅ 已加入待播：{os.path.basename(path)}\n")
        self.update_queue_listbox()
        self.persist_settings()


    def play_previous_song(self):
        if not self.music_files:
            return
        self.clear_queue()
        prev_index = self.get_prev_index()
        if prev_index is None:
            return
        self.current_index = prev_index
        if self.prev_audio_data and self.prev_audio_data[0] == prev_index:
            _, vocals, accomp, sr = self.prev_audio_data
            self.prev_audio_data = None
            threading.Thread(
                target=lambda: self.play_song(prev_index, (vocals, accomp, sr)),
                daemon=True
            ).start()
        else:
            threading.Thread(target=lambda: self.play_song(prev_index), daemon=True).start()

    def play_next_song_manual(self):
        self.auto_next_enabled = False  # 禁止自动续播
        self.clear_queue()
        next_index = self.get_next_index()
        if next_index is not None:
            self.current_index = next_index
            if self.next_audio_data and self.next_audio_data[0] == next_index:
                _, vocals, accomp, sr = self.next_audio_data
                self.next_audio_data = None
                threading.Thread(
                    target=lambda: self.play_song(next_index, (vocals, accomp, sr)),
                    daemon=True
                ).start()
            else:
                threading.Thread(target=lambda: self.play_song(next_index), daemon=True).start()


    def play_song(self, index, preloaded=None):
        if not self.play_lock.acquire(blocking=False):
            return  # 正在播放时不重复执行

        try:
            self.auto_next_enabled = True  # 默认启用自动续播
            self.session_id = str(uuid.uuid4())
            current_session = self.session_id
            self.next_audio_data = None
            old_data = self.current_audio_data
            if self.player:
                self.player.stop()
                self.player = None
            if old_data:
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
            self.player.play()
            if self.audio_path in self.progress_map:
                self.player.seek_to(self.progress_map[self.audio_path])

            self.current_audio_data = (index, vocals, accomp, sr)

            lrc_path = os.path.splitext(self.audio_path)[0] + ".lrc"
            try:
                lyrics = parse_lrc(lrc_path)
                start_lyrics_display(lyrics, self.player, self.lyrics_box)
            except FileNotFoundError:
                self.lyrics_box.insert("end", "⚠️ 未找到歌词文件\n")

            self.progress_bar.config(state=tk.NORMAL)
            self.progress_var.set(self.progress_map.get(self.audio_path, 0) * 100)
            if not self.update_loop_running:
                threading.Thread(target=self.update_progress_loop, daemon=True).start()

            threading.Thread(target=lambda: self.preload_next_song(current_session), daemon=True).start()
            threading.Thread(target=lambda: self.preload_prev_song(current_session), daemon=True).start()
            threading.Thread(target=lambda: self.monitor_and_play_next(current_session), daemon=True).start()

        except Exception as e:
            messagebox.showerror("出错", str(e))
        finally:
            self.play_lock.release()



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
            self.next_audio_data = None
            if self.current_audio_data:
                self.prev_audio_data = self.current_audio_data
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
            self.player.play()
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


    def get_next_index(self, peek=False):
        if not self.music_files:
            return None
        if self.future_queue:
            path = self.future_queue[0]
            if not peek:
                self.future_queue.pop(0)
                self.update_queue_listbox()
                self.persist_settings()
            if path in self.music_files:
                return self.music_files.index(path)
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
        self.persist_settings()

    def change_accomp_volume(self, val):
        if self.player:
            self.player.set_accomp_volume(float(val))
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
        """Return the sounddevice index for the selected microphone."""
        return self.input_device_map.get(self.mic_device.get())

    def get_selected_output_index(self):
        """Return the sounddevice index for the selected output device."""
        return self.output_device_map.get(self.output_device.get())

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
