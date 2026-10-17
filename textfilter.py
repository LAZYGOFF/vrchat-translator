import difflib
import re

ANNOTATION = re.compile(r"[(\[*（【♪][^)\]*）】♪]{0,40}[)\]*）】♪]")

NOISE = re.compile(
    r"(?:[aeo]?(?:h[aeiou]){2,}h?|ha+h?|ho+|(?:[ae]h){2,}[ae]?|(?:ja|ka|ki|ku){2,}|"
    r"l+o+l+|lmf?ao+|rofl|x+d+|kekw?|w{3,}|"
    r"[哈呵嘿嘻笑草嗯啊哦呃唉诶嘛]+|u+m+|u+h+|h+m+|mhm|o+h+|a+h+|pf+t*|wo+w|\d+|"
    r"ага|угу|х+м+|ну+|о+х+|а+х+|[ао]?(?:х[аеиоуэ]){2,}х?|ха+|кхм|"
    r"у+м+|у+х+|э+м*|м+)+")
RU_HESITATION = re.compile(r"а+|э+|м+|э+м+|а+м+")

TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"})
CYRILLIC = re.compile(r"[Ѐ-ӿ]")


LATIN_HINTS = {
    "en": {"the", "and", "is", "are", "you", "what", "how", "yes", "thanks", "hello", "with", "for", "this",
           "that", "it's", "i'm", "don't", "your", "where", "from", "my", "me", "do", "can", "i", "a", "to"},
    "es": {"el", "los", "las", "que", "es", "yo", "tú", "qué", "hola", "gracias", "con", "para", "por", "una",
           "estás", "cómo", "dónde", "eres", "muy", "pero", "sí", "bien", "y", "del", "mi", "te"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "ich", "du", "wir", "ein", "eine", "was", "wie", "bist",
           "auch", "ja", "nein", "danke", "bitte", "mit", "zu", "hallo", "woher", "kommst", "gut", "sehr", "mich"},
    "fr": {"le", "les", "et", "est", "je", "tu", "nous", "vous", "pas", "un", "une", "des", "qui", "oui", "merci",
           "bonjour", "avec", "pour", "c'est", "comment", "où", "très", "salut", "d'où", "mais", "suis", "moi"},
}
LATIN_CHARS = {"es": "ñ¿¡", "de": "äöüß", "fr": "çœàâèêëîïôûù"}


def detect_latin(text):
    low = text.lower()
    words = re.findall(r"[a-zà-ÿœß']+", low)
    if not words:
        return None
    score = {lang: sum(w in hints for w in words) for lang, hints in LATIN_HINTS.items()}
    for lang, chars in LATIN_CHARS.items():
        if any(c in low for c in chars):
            score[lang] += 2
    best = max(score, key=score.get)
    if score[best] == 0 or list(score.values()).count(score[best]) > 1:
        return None
    return best


def _norm(text):
    return re.sub(r"[\W_]+", "", text.lower())


def strip_annotations(text):
    return re.sub(r"\s{2,}", " ", ANNOTATION.sub(" ", text)).strip()


def is_noise(text):
    t = _norm(strip_annotations(text))
    return not t or bool(NOISE.fullmatch(t) or RU_HESITATION.fullmatch(t))


def not_worth_showing(original, translation, target="ru"):
    o, t = _norm(original), _norm(translation)
    if not t or o == t:
        return True
    if not target.lower().startswith("ru"):
        return False
    if not CYRILLIC.search(translation):
        return True
    if CYRILLIC.search(translation) and len(original.split()) >= 2:
        back = _norm(translation.lower().translate(TRANSLIT))
        return difflib.SequenceMatcher(None, o, back).ratio() > 0.75
    return False
