"""包含预加载及自动播放下一曲等核心播放逻辑的混入类。"""

import os
import random
import threading
import time
import uuid
from tkinter import messagebox
import tkinter as tk
import sounddevice as sd

from utils.audio_utils import resample_audio
from audio.separator import separate_audio_in_memory
from audio.player import AudioPlayer


class PlaybackMixin:
    """提供播放相关方法的混入类。"""

    def play_song(self, index, preloaded=None, update_history=True, resume=True, keep_current_as_next=False):
        """播放指定索引的歌曲，可使用预加载的音频数据。"""
        if not self.play_lock.acquire(blocking=False):
            return
        try:
            self.auto_next_enabled = True
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
                else:
                    self.prev_audio_data = old_data
            self.current_audio_data = None
            self.current_index = index

            self.audio_path = self.music_files[index]
            song_name = os.path.basename(self.audio_path)
            self.current_file_label.config(text=f"当前播放：{song_name}")
            self.lyrics_box.delete("1.0", "end")
            self.pause_button.config(state=tk.NORMAL)
            if hasattr(self, "pause_button_lyrics"):
                self.pause_button_lyrics.config(state=tk.NORMAL)

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
            self.current_audio_data = (index, vocals, accomp, sr)

            lrc_path = os.path.splitext(self.audio_path)[0] + ".lrc"
            self.load_and_display_lyrics(lrc_path, self.player)

            self.progress_bar.config(state=tk.NORMAL)
            if hasattr(self, "progress_bar_lyrics"):
                self.progress_bar_lyrics.config(state=tk.NORMAL)
            self.progress_var.set(0)
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
        """在后台线程预加载下一首歌曲。"""
        next_index = self.get_next_index(peek=True)
        if next_index is None or session_id != self.session_id:
            return
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
        except Exception:
            self.next_audio_data = None

    def preload_prev_song(self, session_id):
        """预加载上一首历史歌曲。"""
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
        except Exception:
            self.prev_audio_data = None

    def monitor_and_play_next(self, session_id):
        """监视播放结束并自动开始下一首。"""
        while self.player and self.player.playing and session_id == self.session_id:
            time.sleep(0.5)
        if session_id != self.session_id:
            return
        if not self.auto_next_enabled:
            return
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
            self.progress_var.set(0)
            if not self.update_loop_running:
                threading.Thread(target=self.update_progress_loop, daemon=True).start()
            threading.Thread(target=lambda: self.preload_next_song(self.session_id), daemon=True).start()
            threading.Thread(target=lambda: self.preload_prev_song(self.session_id), daemon=True).start()
            threading.Thread(target=lambda: self.monitor_and_play_next(self.session_id), daemon=True).start()

    def get_next_index(self, peek=False, queue_only=False):
        """根据播放模式和队列返回下一首的索引。"""
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
        """返回上一首歌曲的索引。"""
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

