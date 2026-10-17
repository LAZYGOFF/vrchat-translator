"""Кэш адресов сайтов (DNS) внутри программы.

На некоторых ПК (например, когда VPN-адаптер подсовывает недоступный DNS) поиск адреса по имени
для нового сайта занимает ~10 с, а Windows помнит ответ лишь несколько минут. Из-за этого
«первые переводы» и разогрев шли по 10+ секунд. Здесь адреса
запоминаются на час, при запуске узнаются заранее, а устаревшие обновляются в фоне — перевод
никогда не ждёт DNS. Настройки Windows не меняются.
"""
import socket
import threading
import time

FRESH = 300      # с: столько ответ считается свежим
KEEP = 3600      # с: столько можно отдавать старый ответ, пока в фоне ищется новый

# сайты, к которым ходит программа (перевод, загрузка моделей)
HOSTS = ["api-free.deepl.com", "api.deepl.com", "generativelanguage.googleapis.com", "api.groq.com",
         "translate.google.com", "api.mymemory.translated.net", "huggingface.co"]

_original = socket.getaddrinfo
_cache = {}            # аргументы -> (время, результат)
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
            _refresh_async(key, host, port, args, kwargs)  # отдаём старый адрес, новый ищем в фоне
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
            pass  # не нашёлся — продолжаем отдавать старый адрес
        finally:
            with _lock:
                _refreshing.discard(key)

    threading.Thread(target=run, daemon=True).start()


def install():
    """Включить кэш для всей программы (requests и всё остальное ищут адреса через socket)."""
    socket.getaddrinfo = _cached_getaddrinfo


def prewarm(hosts=HOSTS):
    """Заранее, параллельно, узнать адреса нужных сайтов — в фоне, при запуске."""
    try:
        from urllib3.util.connection import allowed_gai_family
        family = allowed_gai_family()
    except ImportError:
        family = socket.AF_UNSPEC

    def resolve(h):
        try:
            # ровно так же, как спрашивает requests/urllib3 — иначе запись в кэше не совпадёт
            socket.getaddrinfo(h, 443, family, socket.SOCK_STREAM)
        except OSError:
            pass
    for h in hosts:
        threading.Thread(target=resolve, args=(h,), daemon=True).start()
