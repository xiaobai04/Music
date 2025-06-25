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
    """Mixin with miscellaneous helper methods."""

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
        if hasattr(self, "vocal_label"):
            self.vocal_label.config(text=f"🎤 人声 {int(float(val)*100)}%")
        self.persist_settings()

    def change_accomp_volume(self, val):
        if self.player:
            self.player.set_accomp_volume(float(val))
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

    def export_vocals(self):
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
            "lyric_font_size": self.lyrics_font_size.get(),
            "queue": self.future_queue,
            "history": self.play_history,
            "theme": self.theme_choice.get(),
            "language": self.language_choice.get(),
        }
        save_settings(settings)

    def on_close(self):
        self.persist_settings()
        if self.player:
            self.player.stop()
        self.root.destroy()
