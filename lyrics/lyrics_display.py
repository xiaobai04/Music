"""Display scrolling lyrics synchronized with the AudioPlayer."""

import time
import threading

def start_lyrics_display(lyrics, player, text_widget=None, font_size=14):
    """Launch a background thread to update the lyric text widget."""
    manual_scroll_time = 0

    def on_scroll(event=None):
        nonlocal manual_scroll_time
        manual_scroll_time = time.time()

    def center_line(line_number):
        if not text_widget:
            return
        text_widget.see(f"{line_number}.0")

    def display():
        last_index = -1
        while player and (player.playing or player.paused):
            current_time = player.get_current_time()

            idx = 0
            while idx + 1 < len(lyrics) and current_time >= lyrics[idx + 1][0]:
                idx += 1

            if idx != last_index and text_widget:
                text_widget.tag_remove("current", "1.0", "end")
                line_number = idx + 1
                start = f"{line_number}.0"
                end = f"{line_number}.end"
                text_widget.tag_add("current", start, end)
                text_widget.tag_config(
                    "current", foreground="red",
                    font=("Microsoft YaHei", font_size, "bold"))
                if time.time() - manual_scroll_time > 30:
                    center_line(line_number)
                last_index = idx

            time.sleep(0.1)

    if text_widget:
        text_widget.delete("1.0", "end")
        text_widget.tag_config("center", justify="center")
        for _, line in lyrics:
            text_widget.insert("end", line + "\n")
        text_widget.tag_add("center", "1.0", "end")
        text_widget.bind("<MouseWheel>", on_scroll)
        text_widget.bind("<Button-4>", on_scroll)
        text_widget.bind("<Button-5>", on_scroll)
        text_widget.bind("<ButtonPress-1>", on_scroll)

    threading.Thread(target=display, daemon=True).start()
