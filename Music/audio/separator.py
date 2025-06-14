# 文件：audio/separator.py
# 纯内存人声分离（使用 Demucs 模型）

import torch
import torchaudio
from demucs.pretrained import get_model
from demucs.apply import apply_model


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

    # 加载模型
    model = get_model(name="htdemucs").to(device)
    model.eval()

    with torch.no_grad():
        sources = apply_model(
            model,
            wav[None],  # 添加 batch 维度
            device=device,
            split=True,
            overlap=0.25,
            progress=True
        )[0]  # 去掉 batch

    vocals = sources[model.sources.index("vocals")]
    accomp = sources.sum(dim=0) - vocals  # 总和减去人声

    # 转置为 [samples, channels] 并转 numpy
    return vocals.transpose(0, 1).cpu().numpy(), accomp.transpose(0, 1).cpu().numpy(), sr
