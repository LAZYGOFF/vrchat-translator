import os
import re
import threading

SENTENCE_END = re.compile(r"(?<=[.!?…。！？])\s*")

REPO = "JustFrederik/nllb-200-distilled-600M-ct2-int8"
FILES = ["model.bin", "config.json", "shared_vocabulary.txt", "tokenizer.json"]

NLLB = {"ru": "rus_Cyrl", "en": "eng_Latn", "zh": "zho_Hans", "zh-CN": "zho_Hans", "ja": "jpn_Jpan",
        "ko": "kor_Hang", "es": "spa_Latn", "de": "deu_Latn", "fr": "fra_Latn"}


class OfflineTranslator:
    def __init__(self, device="auto", log=print):
        self.device = device
        self.log = log
        self.model = None
        self.backend = ""
        self._lock = threading.Lock()
        self._loading = False

    @property
    def ready(self):
        return self.model is not None

    def load_in_background(self):
        if self.ready or self._loading:
            return
        self._loading = True
        threading.Thread(target=self._load_quiet, daemon=True).start()

    def _load_quiet(self):
        try:
            self.load()
        except Exception as e:
            self.log(f"Офлайн-перевод не загрузился: {e}")
        finally:
            self._loading = False

    def load(self):
        with self._lock:
            if self.model is not None:
                return
            from speech import _add_nvidia_dlls
            _add_nvidia_dlls()
            import ctranslate2
            from huggingface_hub import snapshot_download
            from tokenizers import Tokenizer

            try:
                path = snapshot_download(REPO, allow_patterns=FILES, local_files_only=True)
                self.log("Офлайн-перевод: загрузка модели...")
            except Exception:
                self.log("Офлайн-перевод: первый раз скачиваю модель (~620 МБ)...")
                path = snapshot_download(REPO, allow_patterns=FILES)
            self.tok = Tokenizer.from_file(os.path.join(path, "tokenizer.json"))
            options = []
            if self.device in ("auto", "cuda"):
                options.append(("cuda", "int8"))
            if self.device in ("auto", "cpu"):
                options.append(("cpu", "int8"))
            last = None
            for dev, compute in options:
                try:
                    model = ctranslate2.Translator(path, device=dev, compute_type=compute,
                                                   intra_threads=2, inter_threads=1)
                    self._run(model, "test", "eng_Latn", "rus_Cyrl")
                    self.model, self.backend = model, f"{dev}/{compute}"
                    self.log(f"Офлайн-перевод готов ({self.backend}).")
                    return
                except Exception as e:
                    last = e
            raise RuntimeError(last)

    def _run(self, model, text, src, tgt):
        sentences = [s for s in SENTENCE_END.split(text.strip()) if s.strip()] or [text]
        batch = [[src] + self.tok.encode(s.strip(), add_special_tokens=False).tokens + ["</s>"]
                 for s in sentences]
        results = model.translate_batch(batch, target_prefix=[[tgt]] * len(batch), beam_size=2,
                                        max_decoding_length=200, repetition_penalty=1.1)
        parts = []
        for res in results:
            out = res.hypotheses[0][1:]
            ids = [i for i in (self.tok.token_to_id(t) for t in out) if i is not None]
            parts.append(self.tok.decode(ids, skip_special_tokens=True).strip())
        sep = "" if tgt in ("zho_Hans", "jpn_Jpan") else " "
        return re.sub(r"\s+([,.!?;:…])", r"\1", sep.join(p for p in parts if p))

    def translate(self, text, src, tgt):
        if not self.ready:
            self.load()
        if src not in NLLB or tgt not in NLLB:
            raise RuntimeError(f"офлайн-перевод не знает язык {src if src not in NLLB else tgt}")
        with self._lock:
            if "eng_Latn" in (NLLB[src], NLLB[tgt]):
                return self._run(self.model, text, NLLB[src], NLLB[tgt])
            english = self._run(self.model, text, NLLB[src], "eng_Latn")
            return self._run(self.model, english, "eng_Latn", NLLB[tgt])
