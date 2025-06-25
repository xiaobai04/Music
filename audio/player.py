"""简单的音频播放引擎，支持混入麦克风声音。"""
import sounddevice as sd
import numpy as np
import threading
import collections
from utils.audio_utils import resample_audio

class AudioPlayer:
    """播放分离后的人声和伴奏，可选择混入麦克风。"""

    def __init__(self, vocals, accomp, sample_rate, output_device=None, mic_device=None, mic_enabled=False, latency=0.05):
        """初始化播放器并保存音频数据及设备设置。"""
        self.vocals = vocals
        self.accomp = accomp
        self.mic_input_sr = sample_rate
        self.sample_rate = sample_rate

        self.num_frames = min(len(vocals), len(accomp))
        self.channels = vocals.shape[1]
        self.position = 0
        self.blocksize = 1024
        self.vocal_volume = 1.0
        self.accomp_volume = 1.0
        self.mic_volume = 1.0
        self.playing = False
        self.paused = False
        self.stream = None
        self.mic_stream = None
        self.mic_queue = collections.deque()
        self.mic_channels = self.channels
        self.output_device = output_device
        self.mic_device = mic_device
        self.mic_enabled = mic_enabled
        self.latency = latency
        # 使用可重入锁，允许回调中嵌套调用
        self.lock = threading.RLock()

    def _mic_callback(self, indata, frames, time, status):
        """处理麦克风音频并放入队列以供混音。"""
        with self.lock:
            data = indata.copy()
            if self.mic_input_sr != self.sample_rate:
                data = resample_audio(data, self.mic_input_sr, self.sample_rate)
            if data.shape[1] == 1 and self.channels > 1:
                data = np.repeat(data, self.channels, axis=1)
            elif data.shape[1] > self.channels:
                data = data[:, :self.channels]
            self.mic_queue.append(data)
            if len(self.mic_queue) > 5:
                self.mic_queue.popleft()

    def _callback(self, outdata, frames, time, status):
        """主回调：混合人声、伴奏与麦克风数据。"""
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
            mixed = self.accomp_volume * a_block + self.vocal_volume * v_block

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
        """从头开始播放音频。"""
        if self.playing:
            return
        self.playing = True
        self.paused = False
        self.position = 0
        if self.mic_enabled and self.mic_device is not None:
            self.start_mic(self.mic_device)
        try:
            sd.check_output_settings(device=self.output_device,
                                    samplerate=self.sample_rate,
                                    channels=self.channels,
                                    dtype="float32")
            self.stream = sd.OutputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=self.blocksize,
                dtype="float32",
                callback=self._callback,
                latency=self.latency,
                device=self.output_device,
            )
            self.stream.start()
        except Exception:
            if self.output_device is not None:
                # 指定设备失效时回退到系统默认设备
                self.output_device = None
                try:
                    sd.check_output_settings(device=None,
                                            samplerate=self.sample_rate,
                                            channels=self.channels,
                                            dtype="float32")
                    self.stream = sd.OutputStream(
                        samplerate=self.sample_rate,
                        channels=self.channels,
                        blocksize=self.blocksize,
                        dtype="float32",
                        callback=self._callback,
                        latency=self.latency,
                        device=self.output_device,
                    )
                    self.stream.start()
                    return
                except Exception:
                    self.stream = None
                    
            # 尝试查找可用的输出设备
            for idx, info in enumerate(sd.query_devices()):
                if info.get("max_output_channels", 0) <= 0:
                    continue
                try:
                    sd.check_output_settings(device=idx,
                                            samplerate=self.sample_rate,
                                            channels=self.channels,
                                            dtype="float32")
                    self.stream = sd.OutputStream(
                        samplerate=self.sample_rate,
                        channels=self.channels,
                        blocksize=self.blocksize,
                        dtype="float32",
                        callback=self._callback,
                        latency=self.latency,
                        device=idx,
                    )
                    self.stream.start()
                    self.output_device = idx
                    break
                except Exception:
                    self.stream = None
                    continue

            if self.stream is None:
                self.playing = False
                self.stop_mic()
                raise

    def pause(self):
        """暂停播放并保留当前位置。"""
        with self.lock:
            self.paused = True

    def resume(self):
        """在暂停后继续播放。"""
        with self.lock:
            self.paused = False

    def stop(self):
        """停止播放并重置所有状态。"""
        self.playing = False
        self.paused = False
        if self.stream:
            try:
                # 使用 abort 立即停止播放，避免残留音频
                self.stream.abort()
            except Exception:
                # abort 不可用时退回到 stop
                self.stream.stop()
            self.stream.close()
            self.stream = None
            try:
                # 清空缓冲区，保证完全停止
                sd.stop()
            except Exception:
                pass
        if self.mic_stream:
            self.stop_mic()

    def set_vocal_volume(self, vol):
        """设置人声轨道的音量。"""
        with self.lock:
            self.vocal_volume = float(vol)

    def set_accomp_volume(self, vol):
        """设置伴奏轨道的音量。"""
        with self.lock:
            self.accomp_volume = float(vol)

    def set_mic_volume(self, vol):
        """调整混入的麦克风音量。"""
        with self.lock:
            self.mic_volume = float(vol)

    def change_output_device(self, device):
        """切换到其他输出音频设备。"""
        with self.lock:
            self.output_device = device
            if self.stream:
                was_running = self.playing or self.paused
                self.stream.stop()
                self.stream.close()
                try:
                    self.stream = sd.OutputStream(
                        samplerate=self.sample_rate,
                        channels=self.channels,
                        blocksize=self.blocksize,
                        dtype="float32",
                        callback=self._callback,
                        latency=self.latency,
                        device=self.output_device
                    )
                    if was_running:
                        self.stream.start()
                except Exception:
                    self.stream = None
                    self.output_device = None
                    raise

    def start_mic(self, device=None):
        """开始从指定麦克风采集音频。"""
        with self.lock:
            if device is not None:
                self.mic_device = device
            if self.mic_stream:
                self.stop_mic()
            if self.mic_device is None:
                return
            try:
                info = sd.query_devices(self.mic_device, 'input')
                self.mic_channels = min(info['max_input_channels'], self.channels)
                target_sr = int(info.get('default_samplerate', self.sample_rate)) or self.sample_rate
                if target_sr <= 0 or target_sr > 192000:
                    target_sr = self.sample_rate
                if target_sr > self.sample_rate:
                    target_sr = self.sample_rate
                self.mic_input_sr = target_sr
                self.mic_stream = sd.InputStream(
                    device=self.mic_device,
                    samplerate=self.mic_input_sr,
                    channels=self.mic_channels,
                    blocksize=self.blocksize,
                    dtype='float32',
                    callback=self._mic_callback,
                    latency=self.latency
                )
                self.mic_stream.start()
            except Exception:
                # 麦克风启动失败时禁用功能避免死锁
                self.mic_stream = None
                self.mic_enabled = False
                raise

    def stop_mic(self):
        """停止麦克风采集并清空缓存。"""
        with self.lock:
            if self.mic_stream:
                self.mic_stream.stop()
                self.mic_stream.close()
                self.mic_stream = None
                self.mic_queue.clear()

    def set_mic_enabled(self, enabled, device=None):
        """启用或关闭麦克风输入。"""
        with self.lock:
            self.mic_enabled = bool(enabled)
            if self.mic_enabled:
                self.start_mic(device or self.mic_device)
            else:
                self.stop_mic()

    def get_progress(self):
        """返回播放进度，范围 0 到 1。"""
        return self.position / self.num_frames if self.num_frames else 0.0

    def get_current_time(self):
        """获取当前已播放时间（秒）。"""
        return self.position / self.sample_rate
    
    def seek_to(self, percent):
        """跳转到指定百分比的位置。"""
        with self.lock:
            self.position = int(self.num_frames * percent)
