import concurrent.futures
import functools
import threading

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="audio")


def run(fn, *args, **kwargs):
    if threading.current_thread().name.startswith("audio"):
        return fn(*args, **kwargs)
    return _executor.submit(fn, *args, **kwargs).result()


def on_audio_thread(method):
    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        return run(method, *args, **kwargs)
    return wrapper
