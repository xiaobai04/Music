"""处理播放进度条显示的混入类。"""

import time


class ProgressMixin:
    """负责更新进度条的混入类。"""

    def start_drag(self, event):
        """在用户开始拖动进度条时标记状态。"""
        self.dragging = True

    def update_progress_loop(self):
        """后台循环，定时刷新进度和时间标签。"""
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
        """用户松开进度条后跳转到指定位置。"""
        if self.player:
            percent = self.progress_var.get() / 100
            self.player.seek_to(percent)
        self.dragging = False

    def format_time(self, seconds):
        """将秒数转换为 MM:SS 格式。"""
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"
