# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
import asyncio
from asyncio import Queue

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from typing import Set, AsyncIterable  # noqa
from .Cell import Hash  # noqa


class FileChangedHandler(FileSystemEventHandler):
    def __init__(self, queue: 'Queue[str]') -> None:
        super().__init__()
        self._loop = asyncio.get_event_loop()
        self._queue = queue

    def _queue_modified(self, event: FileSystemEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._queue_modified(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._queue_modified(event)


class Source(AsyncIterable[str]):
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._file_change: 'Queue[str]' = Queue()
        self._observer = Observer()
        self._observer.schedule(FileChangedHandler(queue=self._file_change), '.')

    def __aiter__(self) -> 'Source':
        self._observer.start()
        return self

    async def __anext__(self) -> str:
        while True:
            file = Path(await self._file_change.get())
            if file == self.path:
                return file.read_text()
