# 文件：audio/player.py
import sounddevice as sd
import numpy as np
import threading

class AudioPlayer:
    def __init__(self, vocals, accomp, sample_rate):
        self.vocals = vocals
        self.accomp = accomp
        self.sample_rate = sample_rate

        self.num_frames = min(len(vocals), len(accomp))
        self.channels = vocals.shape[1]
        self.position = 0
        self.blocksize = 1024
        self.vocal_volume = 1.0
        self.playing = False
        self.paused = False
        self.stream = None
        self.lock = threading.Lock()

    def _callback(self, outdata, frames, time, status):
        with self.lock:
            if not self.playing or self.paused:
                outdata[:] = np.zeros((frames, self.channels), dtype='float32')
                return

            end = self.position + frames
            if end >= self.num_frames:
                self.playing = False
                outdata[:] = np.zeros((frames, self.channels), dtype='float32')
                raise sd.CallbackStop()

            v_block = self.vocals[self.position:end]
            a_block = self.accomp[self.position:end]
            mixed = a_block + self.vocal_volume * v_block
            outdata[:len(mixed)] = mixed
            self.position = end

    def play(self):
        if self.playing:
            return
        self.playing = True
        self.paused = False
        self.position = 0
        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            blocksize=self.blocksize,
            dtype='float32',
            callback=self._callback
        )
        self.stream.start()

    def pause(self):
        with self.lock:
            self.paused = True

    def resume(self):
        with self.lock:
            self.paused = False

    def stop(self):
        self.playing = False
        self.paused = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    def set_vocal_volume(self, vol):
        with self.lock:
            self.vocal_volume = float(vol)

    def get_progress(self):
        return self.position / self.num_frames if self.num_frames else 0.0

    def get_current_time(self):
        return self.position / self.sample_rate
    
    def seek_to(self, percent):
        with self.lock:
            self.position = int(self.num_frames * percent)

