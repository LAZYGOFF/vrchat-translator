"""Один постоянный поток для открытия/закрытия звуковых устройств.

Звуковая библиотека (PortAudio, WASAPI) ломается с «Unanticipated host error», если устройства
открывают из разных потоков: например, голос игры уже слушается, а F8 открывает микрофон из
окна. Поэтому все start()/stop() идут сюда, по очереди, в одном и том же потоке.
"""
import concurrent.futures
import functools
import threading

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio")


def run(fn, *args, **kwargs):
    """Выполнить fn в звуковом потоке и дождаться результата (исключения пробрасываются)."""
    if threading.current_thread().name.startswith("audio"):
        return fn(*args, **kwargs)  # уже в нём — иначе поток ждал бы сам себя
    return _executor.submit(fn, *args, **kwargs).result()


def on_audio_thread(method):
    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        return run(method, *args, **kwargs)
    return wrapper
