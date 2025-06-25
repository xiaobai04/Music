"""提供基础音频处理的辅助函数。"""

import numpy as np
import torch
import torchaudio.functional as F

def resample_audio(data: np.ndarray, orig_sr: int, new_sr: int) -> np.ndarray:
    """将 numpy 音频数据重新采样到指定采样率。"""
    if orig_sr == new_sr:
        return data
    tensor = torch.from_numpy(data.T)
    resampled = F.resample(tensor, orig_sr, new_sr)
    return resampled.T.numpy()

