"""Что сейчас играет в Windows: Spotify, Яндекс Музыка, YouTube в браузере, плееры.

Берётся из системных медиа-сессий — того же, что показывает всплывающее окно громкости.
"""
import asyncio
import re
from datetime import datetime, timezone

# onnxruntime (чтение чатбоксов) падает с access violation, если загрузить его ПОСЛЕ winrt.
# Поэтому грузим его раньше — тогда порядок включения «Музыки» и «Чата» не важен.
import onnxruntime  # noqa: F401

from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager as SessionManager,
    GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
)


def _mmss(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


class NowPlaying:
    """Вызывать из одного фонового потока: у него свой цикл asyncio."""

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._manager = None

    def get(self):
        """{"title", "artist", "pos", "end"} того, что играет, или None."""
        return self._loop.run_until_complete(self._get())

    async def _get(self):
        if self._manager is None:
            self._manager = await SessionManager.request_async()
        current = self._manager.get_current_session()
        sessions = ([current] if current else []) + list(self._manager.get_sessions())
        for s in sessions:
            if s.get_playback_info().playback_status != PlaybackStatus.PLAYING:
                continue
            props = await s.try_get_media_properties_async()
            title = (props.title or "").strip()
            if not title:
                continue
            artist = re.sub(r"\s*-\s*Topic$", "", (props.artist or "").strip())  # YouTube «Artist - Topic»
            pos, end = self._progress(s)
            return {"title": title, "artist": artist, "pos": pos, "end": end}
        return None

    @staticmethod
    def _progress(session):
        """Позиция и длина трека, если плеер сообщает их правдоподобно (браузеры часто нет)."""
        try:
            tl = session.get_timeline_properties()
            end = tl.end_time.total_seconds()
            elapsed = (datetime.now(timezone.utc) - tl.last_updated_time).total_seconds()
            pos = tl.position.total_seconds() + max(0.0, elapsed)
            if 0 < end and pos <= end + 2:
                return min(pos, end), end
        except Exception:
            pass
        return None, None


def format_track(track, prefix="♪"):
    artist, title = track["artist"], track["title"]
    # YouTube: «NIVEK FFORHS - Missing Textures» с исполнителем «NIVEK FFORHS» — не повторяем его
    if artist and artist.lower() in title.lower():
        artist = ""
    name = f"{artist} — {title}" if artist else title
    text = f"{prefix} {name}".strip()
    if track["pos"] is not None:
        text += f" [{_mmss(track['pos'])}/{_mmss(track['end'])}]"
    return text
