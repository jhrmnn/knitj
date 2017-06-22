# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
from pprint import pprint
import queue
import json
from typing import NamedTuple
from itertools import cycle
import hashlib
from enum import Enum
import asyncio
from asyncio import Queue

import websockets
import jupyter_client
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from ansi2html import Ansi2HTMLConverter
from misaka import Markdown, HtmlRenderer
from aiohttp import web

# ~~~ typing imports ~~~
from typing import (  # noqa
    TYPE_CHECKING, Any, NewType, Set, Dict, Awaitable, Callable, List,
    Union
)
from mypy_extensions import (  # noqa
    Arg, DefaultArg, NamedArg, DefaultNamedArg, VarArg, KwArg
)
from watchdog.events import FileSystemEvent
WebSocket = websockets.WebSocketServerProtocol
# ~~~ end typing ~~~


Hash = NewType('Hash', str)
Msg = Dict[str, Any]
Data = NewType('Data', str)
MsgId = NewType('MsgId', str)
HTML = NewType('HTML', str)


class Cell:
    class Kind(Enum):
        TEXT = 0
        INPUT = 1
        OUTPUT = 2

    _html_params = {
        Kind.INPUT: ('pre', 'input-cell'),
        Kind.OUTPUT: ('pre', 'output-cell'),
        Kind.TEXT: ('div', 'text-cell'),
    }

    def __init__(self, kind: Kind, content: str, hashid: Hash) -> None:
        self.kind = kind
        self.content = content
        self.hashid = hashid

    def to_html(self, conv: Callable[[str], str] = None) -> HTML:
        elem, klass = Cell._html_params[self.kind]
        content = self.content
        if self.kind == Cell.Kind.TEXT and conv:
            content = conv(content)
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
else:
    FileModifiedQueue = None
    RenderTaskQueue = None
    DataQueue = None


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
        self._md = Markdown(
            HtmlRenderer(),
            extensions='fenced-code math math_explicit tables quote'.split()
        )

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
                self._last_render.htmls.get(cell.hashid) or
                cell.to_html(self._md)  # type: ignore
            ) for cell in document}
        )
        return self._render_msg

    def render_initial(self, nb: Notebook) -> None:
        data = Data(json.dumps(self._render_msg))
        nb.queue_msg(data)

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
        self._hashids: Dict[MsgId, Hash] = {}
        self._input_cells: Dict[Hash, Cell] = {}
        self._conv = Ansi2HTMLConverter()

    async def _get_msg(self,
                       func: Callable[[DefaultNamedArg(int, 'timeout')], Msg],
                       ) -> Msg:
        def partial() -> Msg:
            return func(timeout=1)
        return await self._loop.run_in_executor(None, partial)

    def _get_parent(self, msg: Msg) -> Hash:
        return self._hashids[msg['parent_header']['msg_id']]

    async def _iopub_receiver(self) -> None:
        while True:
            try:
                msg = await self._get_msg(self._client.get_iopub_msg)
            except queue.Empty:
                continue
            if msg['msg_type'] == 'execute_result':
                hashid = self._get_parent(msg)
                cell = Cell(Cell.Kind.OUTPUT, msg['content']['data']['text/plain'], hashid)
                self.renderer.add_task(cell)
            elif msg['msg_type'] == 'stream':
                hashid = self._get_parent(msg)
                assert msg['content']['name'] == 'stdout'
                cell = Cell(Cell.Kind.OUTPUT, msg['content']['text'].strip(), hashid)
                self.renderer.add_task(cell)
            print('IOPUB: ', end='')
            pprint(msg)

    async def _shell_receiver(self) -> None:
        while True:
            try:
                msg = await self._get_msg(self._client.get_shell_msg)
            except queue.Empty:
                continue
            if msg['msg_type'] == 'execute_reply':
                hashid = self._get_parent(msg)
                if msg['content']['status'] == 'ok':
                    pass
                elif msg['content']['status'] == 'error':
                    cell = Cell(
                        Cell.Kind.OUTPUT,
                        self._conv.convert(
                            '\n'.join(msg['content']['traceback']), full=False
                        ),
                        hashid
                    )
                    self.renderer.add_task(cell)
            print('SHELL: ', end='')
            pprint(msg)

    def execute(self, cell: Cell) -> None:
        assert cell.kind == Cell.Kind.INPUT
        msg_id = MsgId(self._client.execute(cell.content))
        self._input_cells[cell.hashid] = cell
        self._hashids[msg_id] = cell.hashid

    def execute_hashid(self, hashid: Hash) -> None:
        self.execute(self._input_cells.pop(hashid))

    async def run(self) -> None:
        kernel = jupyter_client.KernelManager(kernel_name='python3')
        try:
            kernel.start_kernel()
            self._client = kernel.client()
            await asyncio.gather(self._iopub_receiver(), self._shell_receiver())
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
            con = con.strip()
            cells.append(Cell(kind, con.strip(), get_hash(con)))
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

    def _get_response(self, text: str) -> web.Response:
        return web.Response(text=text, content_type='text/html')

    async def handler(self, request: web.BaseRequest) -> web.Response:
        if request.path == '/':
            return self._get_response(self._static['index.html'].replace(
                '<div id="cells"></div>',
                f'<div id="cells">\n{self.renderer.get_last_html()}\n</div>',
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
        renderer.render_initial(nb)
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
