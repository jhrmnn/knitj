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


class CellKind(Enum):
    TEXT = 0
    INPUT = 1
    OUTPUT = 2


class Cell(NamedTuple):
    kind: CellKind
    content: str
    hashid: Hash


if TYPE_CHECKING:
    FileModifiedQueue = Queue[str]
    RenderTaskQueue = Queue[Union[Cell, List[Cell]]]
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


def cell_to_html(cell: Cell) -> HTML:
    elem = {
        CellKind.INPUT: 'pre',
        CellKind.OUTPUT: 'pre',
        CellKind.TEXT: 'p',
    }[cell.kind]
    klass = {
        CellKind.INPUT: 'input-cell',
        CellKind.OUTPUT: 'output-cell',
        CellKind.TEXT: 'text-cell',
    }[cell.kind]
    return HTML(
        f'<{elem} id="{cell.hashid}" class="{klass}">{cell.content}</{elem}>'
    )


class Renderer:
    def __init__(self, notebooks: Set[Notebook]) -> None:
        self.notebooks = notebooks
        self._task_queue: RenderTaskQueue = Queue()

    def add_task(self, task: Union[Cell, List[Cell]]) -> None:
        self._task_queue.put_nowait(task)

    async def run(self) -> None:
        while True:
            task = await self._task_queue.get()
            if isinstance(task, Cell):
                cell = task
                msg: Msg = dict(
                    kind='cell',
                    content=cell_to_html(cell),
                    hashid=cell.hashid
                )
            else:
                cells = task
                msg = dict(
                    kind='document',
                    cells=[cell.hashid for cell in cells],
                    contents={cell.hashid: cell_to_html(cell) for cell in cells},
                )
            data = Data(json.dumps(msg))
            for nb in self.notebooks:
                nb.queue_msg(data)


class Kernel:
    def __init__(self, renderer: Renderer) -> None:
        self.renderer = renderer
        self._loop = asyncio.get_event_loop()
        self._hashids: Dict[MsgId, Hash] = {}
        self._input_cells: Dict[Hash, Cell] = {}

    async def _get_msg(self,
                       func: Callable[[DefaultNamedArg(int, 'timeout')], Msg],
                       ) -> Msg:
        def partial() -> Msg:
            return func(timeout=1)
        return await self._loop.run_in_executor(None, partial)

    async def _iopub_receiver(self) -> None:
        while True:
            try:
                msg = await self._get_msg(self._client.get_iopub_msg)
            except queue.Empty:
                continue
            if msg['msg_type'] == 'execute_result':
                hashid = self._hashids[msg['parent_header']['msg_id']]
                cell = Cell(CellKind.OUTPUT, msg['content']['data']['text/plain'], hashid)
                self.renderer.add_task(cell)
            pprint(msg)

    async def _shell_receiver(self) -> None:
        while True:
            try:
                msg = await self._get_msg(self._client.get_shell_msg)
            except queue.Empty:
                continue
            pprint(msg)

    def execute(self, cell: Cell) -> None:
        assert cell.kind == CellKind.INPUT
        msg_id = MsgId(self._client.execute(cell.content))
        self._input_cells[cell.hashid] = cell
        self._hashids[msg_id] = cell.hashid

    def execute_hashid(self, hashid: Hash) -> None:
        self.execute(self._input_cells[hashid])

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

    async def file_change(self) -> str:
        while True:
            file = Path(await self._queue.get())
            if file == self.path:
                return file.read_text()

    def _parse(self, src: str) -> List[Cell]:
        contents = src.split('```')
        assert len(contents) % 2 == 1
        cells = [
            Cell(kind, con.strip(), get_hash(con)) for kind, con in zip(
                cycle([CellKind.TEXT, CellKind.INPUT]),
                contents
            )
        ]
        return cells

    async def run(self) -> None:
        self._observer.start()
        while True:
            src = await self.file_change()
            cells = self._parse(src)
            self.renderer.add_task(cells)
            for cell in cells:
                if cell.kind == CellKind.INPUT:
                    self.kernel.execute(cell)


async def neptune(path: str) -> None:
    notebooks: Set[Notebook] = set()
    renderer = Renderer(notebooks)
    kernel = Kernel(renderer)
    source = Source(path, kernel, renderer)

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
    )
