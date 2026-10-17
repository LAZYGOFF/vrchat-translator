"""Отправка текста в чатбокс VRChat через OSC (в игре: Action Menu -> Options -> OSC -> Enabled)."""
import socket
import struct
import threading
import time

CHATBOX_LIMIT = 144  # больше VRChat не показывает
# VRChat молча отбрасывает сообщения в чатбокс, если слать чаще ~1.5 с
# (официальной цифры нет; 1.5 с — минимум, на который рассчитаны OSC-программы вроде VRCOSC)
MIN_GAP = 1.6

_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_gap_lock = threading.Lock()
_last_chatbox = 0.0


def _pad(b):
    # строки OSC заканчиваются нулём и дополняются нулями до кратного 4
    return b + b"\0" * (4 - len(b) % 4)


def _send(message, port):
    _sock.sendto(message, ("127.0.0.1", port))


def send_chatbox(text, port=9000, notify=True):
    """Показать text в чатбоксе над головой сразу (без клавиатуры).

    notify=False — без звука уведомления (для музыки, которая обновляется каждые 5 с).
    Пустая строка очищает чатбокс.
    """
    text = text.replace("\n", " ").strip()
    if len(text) > CHATBOX_LIMIT:
        text = text[: CHATBOX_LIMIT - 1] + "…"
    tags = b",sTT" if notify else b",sTF"
    global _last_chatbox
    with _gap_lock:
        # моё сообщение сразу после трека иначе потерялось бы — ждём, сколько нужно
        wait = _last_chatbox + MIN_GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _send(_pad(b"/chatbox/input") + _pad(tags) + _pad(text.encode("utf-8")), port)
        _last_chatbox = time.monotonic()


def set_typing(on, port=9000):
    """Индикатор «печатает...» над головой."""
    _send(_pad(b"/chatbox/typing") + _pad(b",T" if on else b",F"), port)


# ---------- что сообщает сам VRChat (OSC на порт 9001) ----------

def _read_str(data, off):
    end = data.index(b"\0", off)
    return data[off:end].decode("utf-8", "replace"), (end + 4) // 4 * 4


def parse(data):
    """[(адрес, [аргументы])] из OSC-пакета (сообщение или bundle)."""
    if data.startswith(b"#bundle\0"):
        out, off = [], 16
        while off + 4 <= len(data):
            size = struct.unpack(">i", data[off:off + 4])[0]
            out += parse(data[off + 4:off + 4 + size])
            off += 4 + size
        return out
    address, off = _read_str(data, 0)
    tags, off = _read_str(data, off)
    args = []
    for t in tags[1:]:
        if t in "TF":
            args.append(t == "T")
        elif t in "if":
            args.append(struct.unpack(">i" if t == "i" else ">f", data[off:off + 4])[0])
            off += 4
        elif t == "s":
            s, off = _read_str(data, off)
            args.append(s)
        else:
            break  # остальные типы VRChat для нас не шлёт
    return [(address, args)]


class VRChatState:
    """Включён ли у вас микрофон в VRChat (значок внизу: белый — включён, красный — выключен).

    VRChat сам присылает параметр MuteSelf по OSC на порт 9001: при смене аватара и каждый раз,
    когда вы включаете/выключаете микрофон. muted = None — VRChat ещё ничего не прислал.
    """

    def __init__(self, on_change=None, port=9001):
        self.port = port
        self.on_change = on_change
        self.muted = None
        self.error = ""

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("127.0.0.1", self.port))
        except OSError:
            self.error = f"порт {self.port} занят другой OSC-программой"
            return
        while True:
            try:
                data, _ = sock.recvfrom(65536)
                for address, args in parse(data):
                    if address == "/avatar/parameters/MuteSelf" and args:
                        muted = bool(args[0])
                        if muted != self.muted:
                            self.muted = muted
                            if self.on_change:
                                self.on_change(muted)
            except (OSError, ValueError, struct.error):
                continue  # кривой пакет — пропускаем
