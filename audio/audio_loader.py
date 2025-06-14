# audio/audio_loader.py
import librosa

def load_audio(file_path):
    """
    使用 librosa 读取音频，返回波形数据和采样率
    """
    y, sr = librosa.load(file_path, sr=None, mono=False)  # 保持原采样率和通道
    return y, sr
