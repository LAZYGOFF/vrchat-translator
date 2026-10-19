import importlib.util
import os
import re

import numpy as np

from textfilter import CYRILLIC, strip_annotations

HALLUCINATIONS = [
    "谢谢观看", "感谢观看", "谢谢大家收看", "请不吝点赞", "点赞", "订阅", "转发", "打赏",
    "明镜", "点点栏目", "字幕", "优优独播", "yoyo", "amara", "下集再见", "以下是普通话的句子",
    "thanks for watching", "thank you for watching", "subtitles by", "please subscribe",
    "like and subscribe", "продолжение следует", "субтитры", "спасибо за просмотр",
]

PROMPTS = {"zh": "以下是普通话的句子。"}


def _add_nvidia_dlls():
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc"):
        try:
            spec = importlib.util.find_spec(pkg)
        except ModuleNotFoundError:
            continue
        if not spec or not spec.submodule_search_locations:
            continue
        for base in spec.submodule_search_locations:
            bin_dir = os.path.join(base, "bin")
            if os.path.isdir(bin_dir):
                os.add_dll_directory(bin_dir)
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


def _clean(text):
    text = re.sub(r"(.{1,6}?)\1{4,}", r"\1\1\1", text)
    return text.strip(" 　,，.。")


def _is_garbage(text):
    low = text.lower()
    return not text or any(h in low for h in HALLUCINATIONS)


class Recognizer:
    def __init__(self, model_name, device="auto", log=print):
        self.model_name = model_name
        self.device = device
        self.log = log
        self.model = None
        self.backend = ""

    def load(self):
        _add_nvidia_dlls()
        from faster_whisper import WhisperModel

        options = []
        if self.device in ("auto", "cuda"):
            options += [("cuda", "int8"), ("cuda", "int8_float16")]
        if self.device in ("auto", "cpu"):
            options += [("cpu", "int8")]

        last_error = None
        for dev, compute in options:
            try:
                model = WhisperModel(self.model_name, device=dev, compute_type=compute)
                segments, _ = model.transcribe(np.zeros(16000, np.float32), language="zh")
                list(segments)
                self.model, self.backend = model, f"{dev}/{compute}"
                return
            except Exception as e:
                last_error = e
                self.log(f"Не получилось на {dev}/{compute}: {e}")
        raise RuntimeError(f"Модель не загрузилась: {last_error}")

    def transcribe(self, audio, languages=None, detect=True):
        if languages and (detect or len(languages) > 1):
            detected, _, probs = self.model.detect_language(audio)
            p = {}
            for code, prob in probs:
                code = "zh" if code == "yue" else code
                p[code] = p.get(code, 0.0) + prob
            top = max(p, key=p.get)
            if top not in languages or p[top] < 0.3:
                return "", top
            lang = top
        else:
            lang = languages[0] if languages else None
        segments, info = self.model.transcribe(
            audio,
            language=lang,
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
            condition_on_previous_text=False,
            without_timestamps=True,
            initial_prompt=PROMPTS.get(lang or ""),
        )
        parts = []
        for s in segments:
            if s.no_speech_prob > 0.6 and s.avg_logprob < -0.8:
                continue
            if s.avg_logprob < -1.2:
                continue
            parts.append(s.text.strip())

        detected = info.language
        sep = "" if detected in ("zh", "ja") else " "
        text = _clean(strip_annotations(sep.join(parts)))
        if _is_garbage(text):
            return "", detected
        if languages and "ru" not in languages and CYRILLIC.search(text):
            return "", "ru"
        return text, detected
