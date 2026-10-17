FIELDS = [
    ("bg", "Фон окна"),
    ("card", "Фон субтитров и панели"),
    ("card2", "Кнопки и поле ввода"),
    ("fg", "Текст"),
    ("dim", "Подписи и время"),
    ("accent", "Акцент (переключатели)"),
    ("voice", "Голос собеседников"),
    ("chat", "Чат собеседников"),
    ("me", "Мои сообщения"),
    ("music", "Музыка"),
]

PRESETS = {
    "Тёмная": dict(bg="#0e1016", card="#161922", card2="#1d2130", fg="#e8eaf0", dim="#8a90a2",
                   accent="#5aa9ff", voice="#5aa9ff", chat="#ffb547", me="#4ade80", music="#f472b6"),
    "Полночь": dict(bg="#0b1020", card="#111833", card2="#1a2347", fg="#e6ecff", dim="#8b95c9",
                    accent="#7c9cff", voice="#7cc4ff", chat="#ffd166", me="#5eead4", music="#f0abfc"),
    "Графит": dict(bg="#121212", card="#1c1c1c", card2="#2a2a2a", fg="#ececec", dim="#9a9a9a",
                   accent="#60a5fa", voice="#60a5fa", chat="#fbbf24", me="#34d399", music="#f472b6"),
    "Неон": dict(bg="#07070c", card="#0f0f1a", card2="#1b1b33", fg="#f0f0ff", dim="#8888aa",
                 accent="#00e5ff", voice="#00e5ff", chat="#ffe600", me="#39ff88", music="#ff3df2"),
    "Сакура": dict(bg="#1a1016", card="#24161f", card2="#35202e", fg="#fbeaf3", dim="#b993a8",
                   accent="#ff8fc7", voice="#8fc7ff", chat="#ffc38f", me="#9ff0b5", music="#ff8fc7"),
    "Светлая": dict(bg="#eef0f5", card="#ffffff", card2="#e3e6ee", fg="#1a1d26", dim="#646b7d",
                    accent="#2563eb", voice="#2563eb", chat="#c2410c", me="#15803d", music="#be185d"),
}
DEFAULT = "Тёмная"
CUSTOM = "Своя"


def resolve(cfg):
    base = PRESETS.get(cfg.get("theme_preset"), PRESETS[DEFAULT])
    own = cfg.get("theme") or {}
    return {k: _valid(own.get(k)) or base[k] for k, _ in FIELDS}


def _valid(color):
    if isinstance(color, str) and len(color) == 7 and color.startswith("#"):
        try:
            int(color[1:], 16)
            return color.lower()
        except ValueError:
            pass
    return None


def rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def hexcolor(r, g, b):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in (r, g, b))


def mix(a, b, t):
    return hexcolor(*(x + (y - x) * t for x, y in zip(rgb(a), rgb(b))))


def luminance(color):
    r, g, b = rgb(color)
    return 0.299 * r + 0.587 * g + 0.114 * b


def on(color):
    return "#0e1016" if luminance(color) > 150 else "#ffffff"


def key_color(color):
    r, g, b = rgb(color)
    return hexcolor(r, g, b + 1 if b < 255 else b - 1)
