"""在界面中提供杂项辅助功能的混入类。"""

import os
import threading
from tkinter import filedialog, messagebox
import torch
import torchaudio
import sounddevice as sd
try:
    import soundfile as sf
except Exception:
    sf = None

from utils.settings import save_settings


class UtilsMixin:
    """包含各种辅助方法的混入类。"""

    def show_toast(self, message):
        """向用户显示简短提示信息。"""
        try:
            from ttkbootstrap.toast import ToastNotification
            toast = ToastNotification(title="提示", message=message, duration=2000, bootstyle="info")
            toast.show_toast()
        except Exception:
            messagebox.showinfo("提示", message)

    def change_volume(self, val):
        """人声音量滑块变化时的回调。"""
        if self.player:
            self.player.set_vocal_volume(float(val))
        if hasattr(self, "vocal_label"):
            self.vocal_label.config(text=f"🎤 人声 {int(float(val)*100)}%")
        self.persist_settings()

    def change_accomp_volume(self, val):
        """伴奏音量滑块变化时的回调。"""
        if self.player:
            self.player.set_accomp_volume(float(val))
        if hasattr(self, "accomp_label"):
            self.accomp_label.config(text=f"🎶 伴奏 {int(float(val)*100)}%")
        self.persist_settings()

    def change_mic_volume(self, *args):
        """根据变量变动更新麦克风音量。"""
        if self.player:
            self.player.set_mic_volume(float(self.mic_volume.get()))
        self.persist_settings()


    def on_mic_device_change(self, *args):
        """处理麦克风设备切换。"""
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
        """根据复选框状态启用或禁用麦克风。"""
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
        """切换用户选择的输出设备。"""
        self.persist_settings()
        if self.player:
            out_dev = self.get_selected_output_index()
            try:
                self.player.change_output_device(out_dev)
                self.show_toast("已切换输出设备")
            except Exception as e:
                messagebox.showerror("输出设备错误", str(e))

    def export_vocals(self):
        """将当前歌曲的人声导出到文件。"""
        if not self.current_audio_data:
            messagebox.showwarning("未播放", "请先播放歌曲再导出")
            return
        _, vocals, _, sr = self.current_audio_data
        base = os.path.splitext(os.path.basename(self.audio_path))[0]
        default_name = f"{base} - 人声.wav"
        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=[("WAV 文件", "*.wav")], initialfile=default_name)
        if not path:
            return
        threading.Thread(target=self.save_audio_file, args=(path, vocals, sr), daemon=True).start()

    def export_accompaniment(self):
        """将伴奏轨道导出到文件。"""
        if not self.current_audio_data:
            messagebox.showwarning("未播放", "请先播放歌曲再导出")
            return
        _, _, accomp, sr = self.current_audio_data
        base = os.path.splitext(os.path.basename(self.audio_path))[0]
        default_name = f"{base} - 伴奏.wav"
        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=[("WAV 文件", "*.wav")], initialfile=default_name)
        if not path:
            return
        threading.Thread(target=self.save_audio_file, args=(path, accomp, sr), daemon=True).start()

    def save_audio_file(self, path, data, sr):
        """使用 torchaudio 或 soundfile 将音频写入磁盘。"""
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
        """返回当前选中的麦克风设备索引。"""
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
        """返回选定的输出设备索引。"""
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
        """将当前界面设置保存到磁盘。"""
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
            "lyric_font_size": self.lyrics_font_size.get(),
            "queue": self.future_queue,
            "history": self.play_history,
            "theme": self.theme_choice.get(),
            "language": self.language_choice.get(),
        }
        save_settings(settings)

    def on_close(self):
        """处理窗口关闭事件并保存设置。"""
        self.persist_settings()
        if self.player:
            self.player.stop()
        self.root.destroy()
