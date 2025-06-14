# 文件：lyrics/lyrics_display.py
import time
import threading

def start_lyrics_display(lyrics, player, text_widget=None):
    def display():
        last_index = -1
        while player and (player.playing or player.paused):
            current_time = player.get_current_time()

            # 定位当前歌词行索引
            idx = 0
            while idx + 1 < len(lyrics) and current_time >= lyrics[idx + 1][0]:
                idx += 1

            if idx != last_index and text_widget:
                # 清除旧高亮
                text_widget.tag_remove("current", "1.0", "end")

                # 精确高亮第 idx 行（从 1.0 开始）
                line_number = idx + 1
                start = f"{line_number}.0"
                end = f"{line_number}.end"

                text_widget.tag_add("current", start, end)
                text_widget.tag_config("current", foreground="red", font=("Microsoft YaHei", 14, "bold"))
                text_widget.see(start)

                last_index = idx

            time.sleep(0.1)

    # 初始化：显示所有歌词
    if text_widget:
        text_widget.delete("1.0", "end")
        for _, line in lyrics:
            text_widget.insert("end", line + "\n")

    threading.Thread(target=display, daemon=True).start()
