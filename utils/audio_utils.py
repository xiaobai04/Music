"""Helper functions for basic audio processing."""

import numpy as np
import torch
import torchaudio.functional as F

def resample_audio(data: np.ndarray, orig_sr: int, new_sr: int) -> np.ndarray:
    """Resample numpy audio array to a new sample rate."""
    if orig_sr == new_sr:
        return data
    tensor = torch.from_numpy(data.T)
    resampled = F.resample(tensor, orig_sr, new_sr)
    return resampled.T.numpy()

