# 文件：audio/player.py
import sounddevice as sd
import numpy as np
import threading
import collections

class AudioPlayer:
    def __init__(self, vocals, accomp, sample_rate, mic_device=None, mic_enabled=False, latency=0.05):
        self.vocals = vocals
        self.accomp = accomp
        self.sample_rate = sample_rate

        self.num_frames = min(len(vocals), len(accomp))
        self.channels = vocals.shape[1]
        self.position = 0
        self.blocksize = 1024
        self.vocal_volume = 1.0
        self.mic_volume = 1.0
        self.playing = False
        self.paused = False
        self.stream = None
        self.mic_stream = None
        self.mic_queue = collections.deque()
        self.mic_channels = self.channels
        self.mic_device = mic_device
        self.mic_enabled = mic_enabled
        self.latency = latency
        self.lock = threading.Lock()

    def _mic_callback(self, indata, frames, time, status):
        with self.lock:
            data = indata.copy()
            if data.shape[1] == 1 and self.channels > 1:
                data = np.repeat(data, self.channels, axis=1)
            elif data.shape[1] > self.channels:
                data = data[:, :self.channels]
            self.mic_queue.append(data)
            if len(self.mic_queue) > 5:
                self.mic_queue.popleft()

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

            if self.mic_stream and self.mic_queue:
                mic_block = self.mic_queue.popleft()
                if mic_block.shape[0] < frames:
                    pad = np.zeros((frames - mic_block.shape[0], self.channels), dtype='float32')
                    mic_block = np.concatenate([mic_block, pad], axis=0)
                if mic_block.shape[1] < self.channels:
                    mic_block = np.repeat(mic_block, self.channels, axis=1)
                elif mic_block.shape[1] > self.channels:
                    mic_block = mic_block[:, :self.channels]
                mixed += self.mic_volume * mic_block[:frames]

            outdata[:len(mixed)] = mixed
            self.position = end

    def play(self):
        if self.playing:
            return
        self.playing = True
        self.paused = False
        self.position = 0
        if self.mic_enabled and self.mic_device is not None:
            self.start_mic(self.mic_device)
        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            blocksize=self.blocksize,
            dtype='float32',
            callback=self._callback,
            latency=self.latency
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
        if self.mic_stream:
            self.stop_mic()

    def set_vocal_volume(self, vol):
        with self.lock:
            self.vocal_volume = float(vol)

    def set_mic_volume(self, vol):
        with self.lock:
            self.mic_volume = float(vol)

    def start_mic(self, device=None):
        with self.lock:
            if device is not None:
                self.mic_device = device
            if self.mic_stream:
                self.stop_mic()
            if self.mic_device is None:
                return
            info = sd.query_devices(self.mic_device, 'input')
            self.mic_channels = min(info['max_input_channels'], self.channels)
            self.mic_stream = sd.InputStream(
                device=self.mic_device,
                samplerate=self.sample_rate,
                channels=self.mic_channels,
                blocksize=self.blocksize,
                dtype='float32',
                callback=self._mic_callback,
                latency=self.latency
            )
            self.mic_stream.start()

    def stop_mic(self):
        with self.lock:
            if self.mic_stream:
                self.mic_stream.stop()
                self.mic_stream.close()
                self.mic_stream = None
                self.mic_queue.clear()

    def set_mic_enabled(self, enabled, device=None):
        with self.lock:
            self.mic_enabled = bool(enabled)
            if self.mic_enabled:
                self.start_mic(device or self.mic_device)
            else:
                self.stop_mic()

    def get_progress(self):
        return self.position / self.num_frames if self.num_frames else 0.0

    def get_current_time(self):
        return self.position / self.sample_rate
    
    def seek_to(self, percent):
        with self.lock:
            self.position = int(self.num_frames * percent)

