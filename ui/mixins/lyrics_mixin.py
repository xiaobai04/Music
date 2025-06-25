"""Mixin adding lyric display functionality to the UI."""

from lyrics.lrc_parser import parse_lrc
from lyrics.lyrics_display import start_lyrics_display


class LyricsMixin:
    """Mixin for lyrics handling."""

    def load_and_display_lyrics(self, lrc_path, player):
        """Parse the lrc file and start the lyrics display."""
        try:
            lyrics = parse_lrc(lrc_path)
            start_lyrics_display(
                lyrics,
                player,
                self.lyrics_box,
                font_size=self.lyrics_font_size.get(),
            )
        except FileNotFoundError:
            self.lyrics_box.insert("end", "⚠️ 未找到歌词文件\n")

    def increase_font_size(self):
        """Enlarge the lyric font size by one step."""
        size = self.lyrics_font_size.get() + 1
        self.lyrics_font_size.set(size)
        self.lyrics_box.configure(font=("Microsoft YaHei", size))
        self.lyrics_box.tag_config("current", font=("Microsoft YaHei", size, "bold"))
        self.persist_settings()

    def decrease_font_size(self):
        """Reduce the lyric font size, keeping a minimum value."""
        size = max(8, self.lyrics_font_size.get() - 1)
        self.lyrics_font_size.set(size)
        self.lyrics_box.configure(font=("Microsoft YaHei", size))
        self.lyrics_box.tag_config("current", font=("Microsoft YaHei", size, "bold"))
        self.persist_settings()
