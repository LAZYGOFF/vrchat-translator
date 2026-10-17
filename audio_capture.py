"""Захват звука, который играет в наушниках/колонках (WASAPI loopback), и нарезка на фразы."""
import math
import queue
import threading
import time
from collections import deque

import numpy as np
import pyaudiowpatch as pyaudio

from audio_thread import on_audio_thread

SR = 16000          # Whisper ждёт 16 кГц моно
FRAME = 480         # 30 мс
PRE_ROLL = 10       # 0.3 с звука до начала фразы
END_SILENCE = 0.6   # пауза, после которой фраза считается законченной
MAX_PHRASE = 12.0   # длинные фразы режем, чтобы не ждать перевода вечно
MIN_VOICED = 0.35   # слишком короткие всплески звука игнорируем
FLOOR_MARGIN = 10   # речь должна быть громче фона (музыка мира, шум) на столько дБ


def list_output_devices():
    p = pyaudio.PyAudio()
    try:
        return [d["name"] for d in p.get_loopback_device_info_generator()]
    finally:
        p.terminate()


def _find_loopback(p, name):
    loopbacks = list(p.get_loopback_device_info_generator())
    if name:
        for d in loopbacks:
            if d["name"] == name:
                return d
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
    default = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    for d in loopbacks:
        if default["name"] in d["name"]:
            return d
    if loopbacks:
        return loopbacks[0]
    raise RuntimeError("Не найдено устройство вывода звука (WASAPI loopback)")


def _wasapi_inputs(p):
    wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)["index"]
    for i in range(p.get_device_count()):
        d = p.get_device_info_by_index(i)
        if d["hostApi"] == wasapi and d["maxInputChannels"] > 0 and not d.get("isLoopbackDevice"):
            yield d


def _find_input(p, name):
    """Микрофон по имени, иначе микрофон Windows по умолчанию."""
    dev = next((d for d in _wasapi_inputs(p) if d["name"] == name), None)
    if dev is None:
        wasapi = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        if wasapi["defaultInputDevice"] < 0:
            raise RuntimeError("микрофон не найден")
        dev = p.get_device_info_by_index(wasapi["defaultInputDevice"])
    return dev


def list_input_devices():
    p = pyaudio.PyAudio()
    try:
        return [d["name"] for d in _wasapi_inputs(p)]
    finally:
        p.terminate()


class MicRecorder:
    """Запись своего микрофона по кнопке: start() ... stop() -> float32, 16 кГц."""

    def __init__(self, device_name=""):
        self.device_name = device_name
        self.device_label = ""

    @on_audio_thread
    def start(self):
        self._p = pyaudio.PyAudio()
        try:
            dev = _find_input(self._p, self.device_name)
        except RuntimeError:
            self._p.terminate()
            raise
        self.device_label = dev["name"]
        self._channels = dev["maxInputChannels"]
        self._rate = int(dev["defaultSampleRate"])
        self._chunks = []
        self._stream = self._p.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self._rate,
            input=True,
            input_device_index=dev["index"],
            frames_per_buffer=int(self._rate * 0.03),
            stream_callback=lambda data, *a: (self._chunks.append(data), (None, pyaudio.paContinue))[1],
        )

    @on_audio_thread
    def stop(self):
        try:
            self._stream.stop_stream()
            self._stream.close()
        finally:
            self._p.terminate()
        return _to_16k_mono(b"".join(self._chunks), self._channels, self._rate)


def _to_16k_mono(data, channels, rate):
    x = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        x = x[: len(x) // channels * channels].reshape(-1, channels).mean(axis=1)
    if rate == SR:
        return x
    if rate % SR == 0:
        k = rate // SR
        return x[: len(x) // k * k].reshape(-1, k).mean(axis=1)
    n_out = int(len(x) * SR / rate)
    return np.interp(np.linspace(0, len(x), n_out, endpoint=False),
                     np.arange(len(x)), x).astype(np.float32)


class SpeechCapture:
    """Слушает звук и отдаёт в on_phrase готовые фразы (float32, 16 кГц).

    mic=False — звук системы (голоса игроков), mic=True — свой микрофон (авто-режим без F8).
    on_level(db, threshold_db) вызывается ~10 раз в секунду для индикатора громкости.
    in_speech=True, пока идёт фраза.
    """

    def __init__(self, device_name, on_phrase, on_level, get_threshold_db, mic=False,
                 end_silence=END_SILENCE):
        self.device_name = device_name
        self.on_phrase = on_phrase
        self.on_level = on_level
        self.get_threshold_db = get_threshold_db
        self.mic = mic
        self.end_silence = end_silence
        self.in_speech = False
        self.device_label = ""
        self._q = queue.Queue()
        self._running = False

    @on_audio_thread
    def start(self):
        self._p = pyaudio.PyAudio()
        try:
            dev = (_find_input if self.mic else _find_loopback)(self._p, self.device_name)
        except RuntimeError:
            self._p.terminate()
            raise
        self.device_label = dev["name"]
        self._channels = dev["maxInputChannels"]
        self._rate = int(dev["defaultSampleRate"])
        self._stream = self._p.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self._rate,
            input=True,
            input_device_index=dev["index"],
            frames_per_buffer=int(self._rate * 0.03),
            stream_callback=self._callback,
        )
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @on_audio_thread
    def stop(self):
        self._running = False
        try:
            self._stream.stop_stream()
            self._stream.close()
        except Exception:
            pass
        self._p.terminate()

    def _callback(self, in_data, frame_count, time_info, status):
        self._q.put(in_data)
        return (None, pyaudio.paContinue)

    def _run(self):
        pre = deque(maxlen=PRE_ROLL)
        buf, rest = [], np.zeros(0, np.float32)
        in_speech, silence, voiced = False, 0, 0
        last_level = 0.0
        floor = None
        frame_sec = FRAME / SR

        while self._running:
            try:
                x = _to_16k_mono(self._q.get(timeout=0.1), self._channels, self._rate)
            except queue.Empty:
                # Когда в системе тишина, loopback вообще не присылает данные
                if not in_speech:
                    self.on_level(-90.0, self.get_threshold_db())
                    continue
                x = np.zeros(SR // 10, np.float32)

            rest = np.concatenate([rest, x])
            while len(rest) >= FRAME:
                f, rest = rest[:FRAME], rest[FRAME:]
                db = max(-90.0, 20 * math.log10(math.sqrt(float(np.mean(f * f))) + 1e-9))
                # Уровень фона: быстро опускается, медленно (~10 с) поднимается
                if floor is None:
                    floor = db
                floor += (db - floor) * (0.05 if db < floor else 0.003)
                threshold = max(self.get_threshold_db(), floor + FLOOR_MARGIN)
                now = time.monotonic()
                if now - last_level > 0.1:
                    self.on_level(db, threshold)
                    last_level = now

                loud = db > threshold
                if not in_speech:
                    pre.append(f)
                    if loud:
                        in_speech, buf, silence, voiced = True, list(pre), 0, 1
                        pre.clear()
                        self.in_speech = True
                    continue

                buf.append(f)
                if loud:
                    silence, voiced = 0, voiced + 1
                else:
                    silence += 1
                if silence * frame_sec >= self.end_silence or len(buf) * frame_sec >= MAX_PHRASE:
                    if voiced * frame_sec >= MIN_VOICED:
                        self.on_phrase(np.concatenate(buf))
                    in_speech, buf = False, []
                    self.in_speech = False
