"""Озвучка перевода офлайн-голосами Piper (скачиваются в кэш программы, в Windows ничего не ставится).

Если голос Piper не загрузился, пробуем голоса самой Windows.
Звук идёт в VoiceMixer (вместе с вашим микрофоном в Line 1) или прямо в выбранное устройство.
"""
import asyncio
import io
import os
import threading
import time
import wave

import numpy as np
import onnxruntime  # noqa: F401  — до winrt, иначе onnxruntime потом падает (см. media.py)
import pyaudiowpatch as pyaudio

PIPER_REPO = "rhasspy/piper-voices"
PIPER_VOICES = {  # язык перевода -> голос Piper (меняется в config.json: tts_voices)
    "en": "en/en_US/lessac/medium/en_US-lessac-medium",
    "zh": "zh/zh_CN/huayan/medium/zh_CN-huayan-medium",
    "ko": "ko/ko_KR/kss/medium/ko_KR-kss-medium",
    "ja": "ja/ja_JP/hi_fi_captain/medium/ja_JP-hi_fi_captain-medium",  # нужен pyopenjtalk-plus
    "es": "es/es_ES/davefx/medium/es_ES-davefx-medium",
    "de": "de/de_DE/thorsten/medium/de_DE-thorsten-medium",
    "fr": "fr/fr_FR/siwis/medium/fr_FR-siwis-medium",
}


def list_output_devices():
    """Устройства вывода (MME: Windows сама подгоняет частоту звука)."""
    p = pyaudio.PyAudio()
    try:
        mme = p.get_host_api_info_by_type(pyaudio.paMME)["index"]
        return [d["name"] for d in (p.get_device_info_by_index(i) for i in range(p.get_device_count()))
                if d["hostApi"] == mme and d["maxOutputChannels"] > 0]
    finally:
        p.terminate()


def _piper_model(name):
    """Путь к голосу: с диска, а если его ещё нет — скачать (~60 МБ, один раз)."""
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    from huggingface_hub import hf_hub_download
    try:
        path = hf_hub_download(PIPER_REPO, name + ".onnx", local_files_only=True)
        hf_hub_download(PIPER_REPO, name + ".onnx.json", local_files_only=True)
    except Exception:
        path = hf_hub_download(PIPER_REPO, name + ".onnx")
        hf_hub_download(PIPER_REPO, name + ".onnx.json")
    return path


class Speaker:
    """Озвучивает текст в отдельном потоке; busy() — пока звук играет (и чуть после)."""

    def __init__(self, log=print, voices=None, mixer=None):
        self.log = log
        self.voices = {**PIPER_VOICES, **(voices or {})}
        self.mixer = mixer          # VoiceMixer или None — тогда прямо в устройство
        self.speaking = False
        self.last_end = 0.0
        self._piper = {}
        self._lock = threading.Lock()
        self._loop = None

    def busy(self):
        """Звучит озвучка или только что закончилась (эхо в микрофоне/игре ещё не стихло)."""
        return self.speaking or time.monotonic() - self.last_end < 0.8

    def preload(self, lang):
        """Скачать и загрузить голос заранее, чтобы первая фраза не ждала."""
        threading.Thread(target=self._piper_voice, args=(lang,), daemon=True).start()

    def say_async(self, text, lang, device_name):
        threading.Thread(target=self._say, args=(text, lang, device_name), daemon=True).start()

    def _say(self, text, lang, device_name):
        with self._lock:  # фразы не накладываются друг на друга
            try:
                audio = self._synthesize_piper(text, lang) or self._synthesize_windows(text, lang)
                if audio is None:
                    self.log(f"Озвучка: нет голоса для языка «{lang}».")
                    return
                self.speaking = True
                if self.mixer is not None and self.mixer.running:
                    self.mixer.play(*audio)
                else:
                    self._play(*audio, device_name)
            except Exception as e:
                self.log(f"Озвучка: ошибка — {e}")
            finally:
                if self.speaking:
                    self.last_end = time.monotonic()
                self.speaking = False

    # ---- Piper (офлайн, основной) ----

    def _piper_voice(self, lang):
        key = lang.split("-")[0].lower()
        if key not in self.voices:
            return None
        if key not in self._piper:
            from piper import PiperVoice
            self.log(f"Озвучка: загружаю голос ({key})...")
            self._piper[key] = PiperVoice.load(_piper_model(self.voices[key]))
            self.log(f"Озвучка: голос ({key}) готов.")
        return self._piper[key]

    def _synthesize_piper(self, text, lang):
        try:
            voice = self._piper_voice(lang)
        except Exception as e:
            self.log(f"Озвучка: голос Piper не загрузился ({e}), пробую голос Windows.")
            return None
        if voice is None:
            return None
        chunks = list(voice.synthesize(text))
        if not chunks:
            return None
        pcm = np.concatenate([np.frombuffer(c.audio_int16_bytes, np.int16) for c in chunks])
        return chunks[0].sample_rate, pcm

    # ---- голоса Windows (запасной вариант) ----

    def _synthesize_windows(self, text, lang):
        from winrt.windows.media.speechsynthesis import SpeechSynthesizer
        prefix = lang.split("-")[0].lower()
        voice = next((v for v in SpeechSynthesizer.all_voices if v.language.lower().startswith(prefix)), None)
        if voice is None:
            return None
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(self._windows_async(text, voice))

    @staticmethod
    async def _windows_async(text, voice):
        from winrt.windows.media.speechsynthesis import SpeechSynthesizer
        from winrt.windows.storage.streams import DataReader
        synth = SpeechSynthesizer()
        synth.voice = voice
        stream = await synth.synthesize_text_to_stream_async(text)
        reader = DataReader(stream.get_input_stream_at(0))
        await reader.load_async(stream.size)
        data = bytearray(stream.size)
        reader.read_bytes(data)
        with wave.open(io.BytesIO(bytes(data))) as w:
            rate, channels = w.getframerate(), w.getnchannels()
            pcm = np.frombuffer(w.readframes(w.getnframes()), np.int16)
        if channels > 1:
            pcm = pcm.reshape(-1, channels).mean(axis=1).astype(np.int16)
        return rate, pcm

    @staticmethod
    def _play(rate, pcm, device_name):
        p = pyaudio.PyAudio()
        try:
            mme = p.get_host_api_info_by_type(pyaudio.paMME)
            index = mme["defaultOutputDevice"]
            for i in range(p.get_device_count()):
                d = p.get_device_info_by_index(i)
                if d["hostApi"] == mme["index"] and d["maxOutputChannels"] > 0 and d["name"] == device_name:
                    index = i
                    break
            out = p.open(format=pyaudio.paInt16, channels=1, rate=rate, output=True,
                         output_device_index=index)
            out.write(pcm.astype(np.int16).tobytes())
            out.stop_stream()
            out.close()
        finally:
            p.terminate()
