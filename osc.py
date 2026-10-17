import socket
import struct
import threading
import time

CHATBOX_LIMIT = 144
MIN_GAP = 1.6

_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_gap_lock = threading.Lock()
_last_chatbox = 0.0


def _pad(b):
    return b + b"\0" * (4 - len(b) % 4)


def _send(message, port):
    _sock.sendto(message, ("127.0.0.1", port))


def send_chatbox(text, port=9000, notify=True):
    text = text.replace("\n", " ").strip()
    if len(text) > CHATBOX_LIMIT:
        text = text[: CHATBOX_LIMIT - 1] + "…"
    tags = b",sTT" if notify else b",sTF"
    global _last_chatbox
    with _gap_lock:
        wait = _last_chatbox + MIN_GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _send(_pad(b"/chatbox/input") + _pad(tags) + _pad(text.encode("utf-8")), port)
        _last_chatbox = time.monotonic()


def set_typing(on, port=9000):
    _send(_pad(b"/chatbox/typing") + _pad(b",T" if on else b",F"), port)


def _read_str(data, off):
    end = data.index(b"\0", off)
    return data[off:end].decode("utf-8", "replace"), (end + 4) // 4 * 4


def parse(data):
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
            break
    return [(address, args)]


class VRChatState:
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
                continue
