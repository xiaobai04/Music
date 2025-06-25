import threading


class ControlMixin:
    """Mixin for playback control buttons and shortcuts."""

    def toggle_pause(self):
        if self.player:
            if self.player.paused:
                self.player.resume()
                self.pause_button.config(text="⏸ 暂停")
                if hasattr(self, "pause_button_lyrics"):
                    self.pause_button_lyrics.config(text="⏸ 暂停")
            else:
                self.player.pause()
                self.pause_button.config(text="▶ 继续")
                if hasattr(self, "pause_button_lyrics"):
                    self.pause_button_lyrics.config(text="▶ 继续")

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
                        target=lambda: self.play_song(
                            prev_index,
                            (vocals, accomp, sr),
                            update_history=False,
                            resume=False,
                            keep_current_as_next=True,
                        ),
                        daemon=True,
                    ).start()
                else:
                    threading.Thread(
                        target=lambda: self.play_song(
                            prev_index,
                            update_history=False,
                            resume=False,
                            keep_current_as_next=True,
                        ),
                        daemon=True,
                    ).start()
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
                target=lambda: self.play_song(
                    prev_index,
                    (vocals, accomp, sr),
                    update_history=False,
                    resume=False,
                    keep_current_as_next=True,
                ),
                daemon=True,
            ).start()
        else:
            threading.Thread(
                target=lambda: self.play_song(
                    prev_index,
                    update_history=False,
                    resume=False,
                    keep_current_as_next=True,
                ),
                daemon=True,
            ).start()

    def play_next_song_manual(self):
        self.auto_next_enabled = False
        next_index = self.get_next_index()
        if next_index is not None:
            if self.player:
                self.player.stop()
                self.player = None
            self.current_index = next_index
            if self.next_audio_data and self.next_audio_data[0] == next_index:
                _, vocals, accomp, sr = self.next_audio_data
                threading.Thread(
                    target=lambda: self.play_song(
                        next_index, (vocals, accomp, sr), resume=False
                    ),
                    daemon=True,
                ).start()
            else:
                threading.Thread(
                    target=lambda: self.play_song(next_index, resume=False),
                    daemon=True,
                ).start()

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

