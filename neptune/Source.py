# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
from itertools import cycle
import asyncio
from asyncio import Queue

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from .Cell import Cell, get_hash
from .Renderer import Renderer, Document
from .Kernel import Kernel
from .jupyter_messaging.content import MIME

from typing import Set  # noqa
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


class Source:
    def __init__(self, path: str, kernel: Kernel, renderer: Renderer) -> None:
        self.path = Path(path)
        self.kernel = kernel
        self.renderer = renderer
        self._file_change: 'Queue[str]' = Queue()
        self._observer = Observer()
        self._observer.schedule(FileChangedHandler(queue=self._file_change), '.')
        self._last_inputs: Set[Hash] = set()

    async def file_change(self) -> str:
        while True:
            file = Path(await self._file_change.get())
            if file == self.path:
                return file.read_text()

    def _parse(self, src: str) -> Document:
        contents = src.split('```')
        assert len(contents) % 2 == 1
        cells = []
        for kind, con in zip(cycle([Cell.Kind.TEXT, Cell.Kind.INPUT]), contents):
            if kind == Cell.Kind.INPUT:
                if con[:6] == 'python':
                    con = con[6:]
                else:
                    con = f'```{con}```'
                    kind = Cell.Kind.TEXT
                mime = MIME.TEXT_PYTHON
            else:
                mime = MIME.TEXT_MARKDOWN
            con = con.rstrip()
            cells.append(Cell(kind, {mime: con}, get_hash(con)))
        return cells

    async def run(self) -> None:
        self._observer.start()
        while True:
            src = await self.file_change()
            document = self._parse(src)
            self.renderer.add_task(document)
            for cell in document:
                if cell.kind == Cell.Kind.INPUT:
                    if cell.hashid not in self._last_inputs:
                        self.kernel.execute(cell)
            self._last_inputs = set(
                cell.hashid for cell in document if cell.kind == Cell.Kind.INPUT
            )
