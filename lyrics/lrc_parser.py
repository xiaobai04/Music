# lyrics/lrc_parser.py
"""Parse LRC lyric files into time/text pairs."""

import re

def parse_lrc(file_path):
    """
    解析 .lrc 文件，返回按时间排序的歌词列表 [(time_in_seconds, text), ...]
    """
    lyrics = []
    time_tag = re.compile(r'\[(\d+):(\d+\.\d+)]')

    with open(file_path, encoding='utf-8') as f:
        for line in f:
            matches = time_tag.findall(line)
            text = time_tag.sub('', line).strip()
            for minute, second in matches:
                time = int(minute) * 60 + float(second)
                lyrics.append((time, text))
    
    return sorted(lyrics)
