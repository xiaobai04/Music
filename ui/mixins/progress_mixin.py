"""Progress bar handling for showing playback position."""

import time


class ProgressMixin:
    """Mixin handling progress bar updates."""

    def start_drag(self, event):
        """Mark the start of user seeking on the progress bar."""
        self.dragging = True

    def update_progress_loop(self):
        """Background loop updating progress and time labels."""
        self.update_loop_running = True
        while self.player and (self.player.playing or self.player.paused):
            current = self.player.get_current_time()
            total = self.player.num_frames / self.player.sample_rate
            if not self.dragging:
                self.progress_var.set(self.player.get_progress() * 100)
            self.time_label.config(
                text=f"{self.format_time(current)} / {self.format_time(total)}"
            )
            if hasattr(self, "time_label_lyrics"):
                self.time_label_lyrics.config(
                    text=f"{self.format_time(current)} / {self.format_time(total)}"
                )
            time.sleep(0.2)
        self.update_loop_running = False

    def on_seek(self, event):
        """Handle releasing the progress bar after seeking."""
        if self.player:
            percent = self.progress_var.get() / 100
            self.player.seek_to(percent)
        self.dragging = False

    def format_time(self, seconds):
        """Convert seconds to MM:SS format."""
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"
