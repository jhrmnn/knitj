# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os
import logging
from pathlib import Path
import asyncio
from asyncio import Queue

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from .cell import Hash  # noqa

from typing import Callable

log = logging.getLogger('knitj.source')


class FileChangedHandler(FileSystemEventHandler):
    def __init__(self, queue: 'Queue[str]') -> None:
        super().__init__()
        self._loop = asyncio.get_event_loop()
        self._queue = queue

    def _queue_modified(self, event: FileSystemEvent) -> None:
        # Must be done this way because watchdog doesn't support asyncio
        # and the on_modified, on_created functions are run in different thread
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._queue_modified(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._queue_modified(event)


class SourceWatcher:
    def __init__(self, handler: Callable[[str], None], path: os.PathLike) -> None:
        self._path = Path(path)
        self._handler = handler
        self._file_change: 'Queue[str]' = Queue()
        self._observer = Observer()
        self._observer.schedule(
            FileChangedHandler(queue=self._file_change), str(self._path.parent)
        )

    async def run(self) -> None:
        self._observer.start()
        log.info(f'Started watching file {self._path} for changes')
        while True:
            file = Path(await self._file_change.get())
            if file == self._path:
                self._handler(file.read_text())
