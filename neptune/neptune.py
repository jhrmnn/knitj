# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
from itertools import cycle, chain
import hashlib
import asyncio
from asyncio import Queue

import ansi2html
import websockets
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from aiohttp import web
from pygments.formatters import HtmlFormatter
from jinja2 import Template

from .jupyter_messaging.content import MIME
from .Cell import Cell, Hash
from .Notebook import Notebook
from .Renderer import Renderer, Document
from .Kernel import Kernel

from typing import (  # noqa
    TYPE_CHECKING, Any, NewType, Set, Dict, Awaitable, Callable, List,
    Union
)

WebSocket = websockets.WebSocketServerProtocol


if TYPE_CHECKING:
    FileModifiedQueue = Queue[str]
else:
    FileModifiedQueue = None


class FileChangedHandler(FileSystemEventHandler):
    def __init__(self, queue: FileModifiedQueue) -> None:
        super().__init__()
        self._loop = asyncio.get_event_loop()
        self._queue = queue

    def _queue_modified(self, event: FileSystemEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event.src_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        self._queue_modified(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._queue_modified(event)


def get_hash(s: str) -> Hash:
    return Hash(hashlib.sha1(s.encode()).hexdigest())


class Source:
    def __init__(self, path: str, kernel: Kernel, renderer: Renderer) -> None:
        self.path = Path(path)
        self.kernel = kernel
        self.renderer = renderer
        self._queue: FileModifiedQueue = Queue()
        self._observer = Observer()
        self._observer.schedule(FileChangedHandler(queue=self._queue), '.')
        self._last_inputs: Set[Hash] = set()

    async def file_change(self) -> str:
        while True:
            file = Path(await self._queue.get())
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


class WebServer:
    def __init__(self, renderer: Renderer) -> None:
        self.renderer = renderer
        self._root = Path(__file__).parents[1]/'client'

    def _get_response(self, text: str) -> web.Response:
        return web.Response(text=text, content_type='text/html')

    async def handler(self, request: web.BaseRequest) -> web.Response:
        if request.path == '/':
            return self._get_response(
                Template((self._root/'templates/index.html').read_text()).render(
                    cells=self.renderer.get_last_html(),
                    styles='\n'.join(chain(
                        [HtmlFormatter().get_style_defs()],
                        map(str, ansi2html.style.get_styles())
                    ))
                )
            )
        try:
            text = (self._root/'static'/request.path[1:]).read_text()
        except FileNotFoundError:
            raise web.HTTPNotFound()
        return self._get_response(text)

    async def run(self) -> None:
        server = web.Server(self.handler)
        loop = asyncio.get_event_loop()
        await loop.create_server(server, '127.0.0.1', 8080)  # type: ignore


async def neptune(path: str) -> None:
    notebooks: Set[Notebook] = set()
    renderer = Renderer(notebooks)
    kernel = Kernel(renderer)
    source = Source(path, kernel, renderer)
    webserver = WebServer(renderer)

    async def handler(ws: WebSocket, path: str) -> None:
        nb = Notebook(ws, kernel)
        notebooks.add(nb)
        await nb.run()
        notebooks.remove(nb)

    await asyncio.gather(
        websockets.serve(handler, 'localhost', 6060),
        renderer.run(),
        source.run(),
        kernel.run(),
        webserver.run(),
    )
