import socket
import threading
import time

FRESH = 300
KEEP = 3600

HOSTS = ["api-free.deepl.com", "api.deepl.com", "generativelanguage.googleapis.com", "api.groq.com",
         "translate.google.com", "api.mymemory.translated.net", "huggingface.co"]

_original = socket.getaddrinfo
_cache = {}
_refreshing = set()
_lock = threading.Lock()


def _cached_getaddrinfo(host, port, *args, **kwargs):
    key = (host, port, args, tuple(sorted(kwargs.items())))
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
    if hit:
        age = now - hit[0]
        if age < FRESH:
            return hit[1]
        if age < KEEP:
            _refresh_async(key, host, port, args, kwargs)
            return hit[1]
    result = _original(host, port, *args, **kwargs)
    with _lock:
        _cache[key] = (time.monotonic(), result)
    return result


def _refresh_async(key, host, port, args, kwargs):
    with _lock:
        if key in _refreshing:
            return
        _refreshing.add(key)

    def run():
        try:
            result = _original(host, port, *args, **kwargs)
            with _lock:
                _cache[key] = (time.monotonic(), result)
        except OSError:
            pass
        finally:
            with _lock:
                _refreshing.discard(key)

    threading.Thread(target=run, daemon=True).start()


def install():
    socket.getaddrinfo = _cached_getaddrinfo


def prewarm(hosts=HOSTS):
    try:
        from urllib3.util.connection import allowed_gai_family
        family = allowed_gai_family()
    except ImportError:
        family = socket.AF_UNSPEC

    def resolve(h):
        try:
            socket.getaddrinfo(h, 443, family, socket.SOCK_STREAM)
        except OSError:
            pass
    for h in hosts:
        threading.Thread(target=resolve, args=(h,), daemon=True).start()
