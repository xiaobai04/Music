"""借助 Demucs 模型将歌曲中的人声与伴奏分离的工具函数。"""

import torch
import torchaudio
from demucs.pretrained import get_model
from demucs.apply import apply_model

_MODEL_CACHE = {}


def _get_model(device: str):
    """按设备缓存并返回 Demucs 模型实例。"""
    model = _MODEL_CACHE.get(device)
    if model is None:
        model = get_model(name="htdemucs").to(device)
        model.eval()
        _MODEL_CACHE[device] = model
    return model


def separate_audio_in_memory(audio_path, device):
    """
    使用 Demucs 在内存中分离音频，返回 (vocals, accompaniment, sample_rate)
    - audio_path: 音频文件路径
    - device: 'cpu' 或 'cuda'
    """
    wav, sr = torchaudio.load(audio_path)

    # 如果是单声道，复制为双声道
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)

    wav = wav.to(torch.float32).to(device)

    # 加载模型（仅首次加载）
    model = _get_model(device)

    with torch.no_grad():
        sources = apply_model(
            model,
            wav[None],  # 添加 batch 维度
            device=device,
            split=True,
            overlap=0.25,
            progress=False
        )[0]  # 去掉 batch

    vocals = sources[model.sources.index("vocals")]
    accomp = sources.sum(dim=0) - vocals  # 总和减去人声

    # 转置为 [samples, channels] 并转 numpy
    return vocals.transpose(0, 1).cpu().numpy(), accomp.transpose(0, 1).cpu().numpy(), sr
