# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
import asyncio
from asyncio import Queue

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class FileChangedHandler(FileSystemEventHandler):
    def __init__(self, *args, queue, **kwargs):
        super().__init__(*args, **kwargs)
        self._loop = asyncio.get_event_loop()
        self._queue = queue

    def on_modified(self, event):
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event.src_path)


async def handler(file):
    print('Modified!', file)


async def neptune(*, watched):
    watched = Path(watched)
    queue = Queue()
    observer = Observer()
    observer.schedule(FileChangedHandler(queue=queue), '.')
    observer.start()
    try:
        while True:
            file = Path(await queue.get())
            if file == watched:
                await handler(watched)
    finally:
        observer.stop()
        observer.join()
