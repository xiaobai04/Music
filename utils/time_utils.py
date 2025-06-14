# utils/time_utils.py

def seconds_to_timestamp(seconds: float) -> str:
    """
    将秒数转成 mm:ss.xx 格式字符串
    """
    minutes = int(seconds) // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:05.2f}"

def timestamp_to_seconds(timestamp: str) -> float:
    """
    将字符串格式的时间戳 [mm:ss.xx] 转为秒数
    """
    try:
        minutes, seconds = timestamp.strip().split(":")
        return int(minutes) * 60 + float(seconds)
    except ValueError:
        return 0.0
