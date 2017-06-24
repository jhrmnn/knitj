# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
import queue
import json
from typing import NamedTuple
from itertools import cycle
from pprint import pprint
import hashlib
import html
from enum import Enum
import asyncio
from asyncio import Queue

import websockets
import jupyter_client
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
import ansi2html
from misaka import Markdown, HtmlRenderer
from aiohttp import web
import pygments
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer
from jinja2 import Template

from . import jupyter_messaging as jupy
from .jupyter_messaging import UUID
from .jupyter_messaging.content import MIME

from typing import (  # noqa
    TYPE_CHECKING, Any, NewType, Set, Dict, Awaitable, Callable, List,
    Union
)

WebSocket = websockets.WebSocketServerProtocol

_md = Markdown(
    HtmlRenderer(),
    extensions='fenced-code math math_explicit tables quote'.split()
)

Hash = NewType('Hash', str)
Msg = Dict[str, Any]
Data = NewType('Data', str)
HTML = NewType('HTML', str)


class Cell:
    class Kind(Enum):
        TEXT = 0
        INPUT = 1
        OUTPUT = 2

    _html_params = {
        Kind.INPUT: ('div', 'input-cell'),
        Kind.OUTPUT: ('pre', 'output-cell'),
        Kind.TEXT: ('div', 'text-cell'),
    }

    def __init__(self, kind: Kind, content: Dict[MIME, str], hashid: Hash) -> None:
        self.kind = kind
        self.content = content
        self.hashid = hashid

    def __repr__(self) -> str:
        return f'<Cell kind={self.kind!r} hashid={self.hashid!r} content={self.content!r}>'

    def to_html(self) -> HTML:
        if MIME.IMAGE_PNG in self.content:
            content = f'<img src="data:image/png;base64,{self.content[MIME.IMAGE_PNG]}">'
        elif MIME.TEXT_HTML in self.content:
            content = self.content[MIME.TEXT_HTML]
        elif MIME.TEXT_MARKDOWN in self.content:
            content = _md(self.content[MIME.TEXT_MARKDOWN])
        elif MIME.TEXT_PLAIN in self.content:
            content = html.escape(self.content[MIME.TEXT_PLAIN])
        elif MIME.TEXT_PYTHON in self.content:
            content = pygments.highlight(
                self.content[MIME.TEXT_PYTHON], PythonLexer(), HtmlFormatter()
            )
        else:
            raise ValueError(f'Unknown MIME types: {list(self.content)}')
        elem, klass = Cell._html_params[self.kind]
        return HTML(
            f'<{elem} id="{self.hashid}" class="{klass}">{content}</{elem}>'
        )


class Render(NamedTuple):
    hashids: List[Hash]
    htmls: Dict[Hash, HTML]


Document = List[Cell]
RenderTask = Union[Cell, Document]
if TYPE_CHECKING:
    FileModifiedQueue = Queue[str]
    RenderTaskQueue = Queue[RenderTask]
    DataQueue = Queue[Data]
    MsgQueue = Queue[Dict]
else:
    FileModifiedQueue = None
    RenderTaskQueue = None
    DataQueue = None
    MsgQueue = None


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


class Notebook:
    def __init__(self, ws: WebSocket, kernel: 'Kernel') -> None:
        print('Got client:', ws)
        self.ws = ws
        self.kernel = kernel
        self._msg_queue: DataQueue = Queue()

    async def _sender(self) -> None:
        while True:
            msg = await self._msg_queue.get()
            await self.ws.send(msg)

    async def _receiver(self) -> None:
        while True:
            data = await self.ws.recv()
            msg = json.loads(data)
            if msg['kind'] == 'reevaluate':
                self.kernel.execute_hashid(msg['hashid'])
            print(self.ws, data)

    def queue_msg(self, msg: Data) -> None:
        self._msg_queue.put_nowait(msg)

    async def run(self) -> None:
        try:
            await asyncio.gather(self._sender(), self._receiver())
        except websockets.ConnectionClosed as e:
            print('Notebook disconnected:', self.ws)


class Renderer:
    def __init__(self, notebooks: Set[Notebook]) -> None:
        self.notebooks = notebooks
        self._task_queue: RenderTaskQueue = Queue()
        self._last_render = Render([], {})

    def add_task(self, task: RenderTask) -> None:
        self._task_queue.put_nowait(task)

    def _render_cell(self, cell: Cell) -> Msg:
        html = cell.to_html()
        self._last_render.htmls[cell.hashid] = html
        return dict(
            kind='cell',
            hashid=cell.hashid,
            html=html,
        )

    @property
    def _render_msg(self) -> Msg:
        return dict(
            kind='document',
            hashids=self._last_render.hashids,
            htmls=self._last_render.htmls,
        )

    def _render_document(self, document: Document) -> Msg:
        self._last_render = Render(
            [cell.hashid for cell in document],
            {cell.hashid: (
                self._last_render.htmls.get(cell.hashid) or cell.to_html()
            ) for cell in document}
        )
        return self._render_msg

    def get_last_html(self) -> HTML:
        return HTML('\n'.join(
            self._last_render.htmls[hashid]
            for hashid in self._last_render.hashids
        ))

    async def run(self) -> None:
        while True:
            task = await self._task_queue.get()
            if isinstance(task, Cell):
                msg = self._render_cell(task)
            elif isinstance(task, list):
                msg = self._render_document(task)
            data = Data(json.dumps(msg))
            for nb in self.notebooks:
                nb.queue_msg(data)


class Kernel:
    def __init__(self, renderer: Renderer) -> None:
        self.renderer = renderer
        self._loop = asyncio.get_event_loop()
        self._hashids: Dict[UUID, Hash] = {}
        self._input_cells: Dict[Hash, Cell] = {}
        self._conv = ansi2html.Ansi2HTMLConverter()
        self._msg_queue: MsgQueue = Queue()

    async def _iopub_receiver(self) -> None:
        def partial() -> Dict:
            return self._client.get_iopub_msg(timeout=1)  # type: ignore
        while True:
            try:
                dct = await self._loop.run_in_executor(None, partial)
            except queue.Empty:
                continue
            self._msg_queue.put_nowait(dct)

    async def _shell_receiver(self) -> None:
        def partial() -> Dict:
            return self._client.get_shell_msg(timeout=1)  # type: ignore
        while True:
            try:
                dct = await self._loop.run_in_executor(None, partial)
            except queue.Empty:
                continue
            self._msg_queue.put_nowait(dct)

    def _get_parent(self, msg: jupy.Message) -> Hash:
        assert msg.parent_header
        return self._hashids[msg.parent_header.msg_id]

    async def _msg_handler(self) -> None:
        while True:
            dct = await self._msg_queue.get()
            try:
                msg = jupy.parse(dct)
            except (TypeError, ValueError):
                pprint(dct)
                raise
            print(msg)
            if isinstance(msg, jupy.EXECUTE_RESULT):
                hashid = self._get_parent(msg)
                cell = Cell(Cell.Kind.OUTPUT, msg.content.data, hashid)
                self.renderer.add_task(cell)
            elif isinstance(msg, jupy.STREAM):
                hashid = self._get_parent(msg)
                cell = Cell(
                    Cell.Kind.OUTPUT,
                    {MIME.TEXT_PLAIN: msg.content.text.strip()},
                    hashid
                )
                self.renderer.add_task(cell)
            elif isinstance(msg, jupy.DISPLAY_DATA):
                hashid = self._get_parent(msg)
                cell = Cell(Cell.Kind.OUTPUT, msg.content.data, hashid)
                self.renderer.add_task(cell)
            elif isinstance(msg, jupy.EXECUTE_REPLY):
                hashid = self._get_parent(msg)
                if isinstance(msg.content, jupy.content.ERROR):
                    cell = Cell(
                        Cell.Kind.OUTPUT,
                        {MIME.TEXT_HTML: self._conv.convert(
                            '\n'.join(msg.content.traceback), full=False
                        )},
                        hashid
                    )
                    self.renderer.add_task(cell)

    def execute(self, cell: Cell) -> None:
        assert cell.kind == Cell.Kind.INPUT
        msg_id = UUID(self._client.execute(cell.content[MIME.TEXT_PYTHON]))
        self._input_cells[cell.hashid] = cell
        self._hashids[msg_id] = cell.hashid

    def execute_hashid(self, hashid: Hash) -> None:
        self.execute(self._input_cells.pop(hashid))

    async def run(self) -> None:
        kernel = jupyter_client.KernelManager(kernel_name='python3')
        try:
            kernel.start_kernel()
            self._client = kernel.client()
            await asyncio.gather(
                self._msg_handler(),
                self._iopub_receiver(),
                self._shell_receiver()
            )
        finally:
            self._client.shutdown()


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
        self._static = {
            path.name: path.read_text()
            for path in (Path(__file__).parents[1]/'client/static').glob('*')
        }
        self._templates = {
            path.name: Template(path.read_text())
            for path in (Path(__file__).parents[1]/'client/templates').glob('*')
        }

    def _get_response(self, text: str) -> web.Response:
        return web.Response(text=text, content_type='text/html')

    async def handler(self, request: web.BaseRequest) -> web.Response:
        if request.path == '/':
            return self._get_response(self._templates['index.html'].render(
                cells=self.renderer.get_last_html(),
                styles=(
                    HtmlFormatter().get_style_defs() + '\n' +
                    '\n'.join(str(rule) for rule in ansi2html.style.get_styles())
                )
            ))
        path = request.path[1:]
        if path in self._static:
            return self._get_response(self._static[path])
        raise web.HTTPNotFound()

    async def run(self) -> None:
        server = web.Server(self.handler)
        await asyncio.get_event_loop().create_server(server, '127.0.0.1', 8080)  # type: ignore


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
