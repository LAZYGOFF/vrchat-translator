import itertools
import threading
import time

import numpy as np
import pyaudiowpatch as pyaudio

from audio_capture import _find_input
from audio_thread import on_audio_thread

JITTER = 0.02
MAX_LAG = 0.08


def vrchat_mics(default_in):
    import winreg
    mics = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\VRChat\VRChat") as key:
            for i in itertools.count():
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                except OSError:
                    break
                for mode, tag in (("VR", "_VR_"), ("ПК", "_Desktop_")):
                    if name.startswith("VRC_INPUT_MIC_DEVICE_NAME" + tag) and isinstance(value, bytes):
                        mics[mode] = value.rstrip(b"\0").decode("utf-8", "replace") or default_in
    except OSError:
        pass
    return mics


def _resample(x, src, dst):
    if src == dst or len(x) == 0:
        return x
    n = int(len(x) * dst / src)
    return np.interp(np.linspace(0, len(x), n, endpoint=False), np.arange(len(x)), x).astype(np.float32)


class VoiceMixer:
    def __init__(self, mic_name, out_name, log=print, mic_gain=1.0):
        self.mic_name, self.out_name = mic_name, out_name
        self.log = log
        self.mic_gain = mic_gain
        self.running = False
        self.mic_label = ""
        self.default_in = ""
        self._lock = threading.Lock()
        self._mic = np.zeros(0, np.float32)
        self._tts = np.zeros(0, np.float32)
        self._primed = False

    @on_audio_thread
    def start(self):
        p = pyaudio.PyAudio()
        try:
            wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
            outs = [d for d in (p.get_device_info_by_index(i) for i in range(p.get_device_count()))
                    if d["hostApi"] == wasapi and d["maxOutputChannels"] > 0 and not d.get("isLoopbackDevice")]
            out = next((d for d in outs if d["name"] == self.out_name or d["name"].startswith(self.out_name)), None)
            if out is None:
                raise RuntimeError(f"нет устройства «{self.out_name}»")
            mic = _find_input(p, self.mic_name)
            if mic["name"].split(" (")[0] == out["name"].split(" (")[0]:
                raise RuntimeError("микрофон и устройство озвучки совпадают — получится петля")
            self.rate, self.channels = int(out["defaultSampleRate"]), out["maxOutputChannels"]
            self._mic_rate, self._mic_channels = int(mic["defaultSampleRate"]), mic["maxInputChannels"]
            self.mic_label = mic["name"]
            default_in = p.get_host_api_info_by_type(pyaudio.paWASAPI)["defaultInputDevice"]
            self.default_in = p.get_device_info_by_index(default_in)["name"] if default_in >= 0 else ""
            self._out = p.open(format=pyaudio.paInt16, channels=self.channels, rate=self.rate, output=True,
                               output_device_index=out["index"], frames_per_buffer=int(self.rate * 0.01),
                               stream_callback=self._out_cb)
            self._in = p.open(format=pyaudio.paInt16, channels=self._mic_channels, rate=self._mic_rate,
                              input=True, input_device_index=mic["index"],
                              frames_per_buffer=int(self._mic_rate * 0.01), stream_callback=self._in_cb)
        except Exception:
            p.terminate()
            raise
        self._p = p
        self.running = True

    @on_audio_thread
    def stop(self):
        self.running = False
        for s in (getattr(self, "_in", None), getattr(self, "_out", None)):
            try:
                s.stop_stream()
                s.close()
            except Exception:
                pass
        try:
            self._p.terminate()
        except Exception:
            pass

    def play(self, rate, pcm):
        x = _resample(pcm.astype(np.float32) / 32768, rate, self.rate)
        with self._lock:
            self._tts = np.concatenate([self._tts, x])
            left = len(self._tts) / self.rate
        time.sleep(left + 0.05)

    def _in_cb(self, data, frame_count, time_info, status):
        x = np.frombuffer(data, np.int16).astype(np.float32) / 32768
        if self._mic_channels > 1:
            x = x[: len(x) // self._mic_channels * self._mic_channels].reshape(-1, self._mic_channels).mean(axis=1)
        x = _resample(x, self._mic_rate, self.rate)
        with self._lock:
            self._mic = np.concatenate([self._mic, x])
            if len(self._mic) > MAX_LAG * self.rate:
                self._mic = self._mic[-int(JITTER * self.rate):]
        return (None, pyaudio.paContinue)

    def _out_cb(self, in_data, frame_count, time_info, status):
        with self._lock:
            if not self._primed and len(self._mic) >= JITTER * self.rate:
                self._primed = True
            if self._primed and len(self._mic) >= frame_count:
                mic, self._mic = self._mic[:frame_count], self._mic[frame_count:]
            else:
                mic = np.zeros(frame_count, np.float32)
                self._primed = False
            tts, self._tts = self._tts[:frame_count], self._tts[frame_count:]
        y = mic * self.mic_gain
        y[: len(tts)] += tts
        y = (np.clip(y, -1, 1) * 32767).astype(np.int16)
        if self.channels > 1:
            y = np.repeat(y, self.channels)
        return (y.tobytes(), pyaudio.paContinue)
