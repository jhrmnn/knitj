# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
from pprint import pprint
import queue
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
    TYPE_CHECKING, Any, NewType, Set, Dict, Awaitable, Callable, List
)
from mypy_extensions import (  # noqa
    Arg, DefaultArg, NamedArg, DefaultNamedArg, VarArg, KwArg
)
from watchdog.events import FileSystemEvent
WebSocket = websockets.WebSocketServerProtocol
# ~~~ end typing ~~~


Hash = NewType('Hash', str)
MsgId = NewType('MsgId', str)


class CellKind(Enum):
    TEXT = 0
    CODE = 1


class Cell(NamedTuple):
    kind: CellKind
    content: str
    hashid: Hash


if TYPE_CHECKING:
    FileModifiedQueue = Queue[str]
    CellQueue = Queue[Cell]
else:
    FileModifiedQueue = None
    CellQueue = None


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
    def __init__(self, ws: WebSocket) -> None:
        print('Got client:', ws)
        self.ws = ws
        self._cell_queue: CellQueue = Queue()

    async def _sender(self) -> None:
        while True:
            cell = await self._cell_queue.get()
            await self.ws.send(cell.content)

    async def _receiver(self) -> None:
        while True:
            data = await self.ws.recv()
            print(self.ws, data)

    def add_cell(self, cell: Cell) -> None:
        self._cell_queue.put_nowait(cell)

    async def run(self) -> None:
        try:
            await asyncio.gather(self._sender(), self._receiver())
        except websockets.ConnectionClosed as e:
            print('Notebook disconnected:', self.ws)


class Kernel:
    def __init__(self, notebooks: Set[Notebook]) -> None:
        self.notebooks = notebooks
        self._loop = asyncio.get_event_loop()
        self._hashids: Dict[MsgId, Hash] = {}

    async def _get_msg(self,
                       func: Callable[[DefaultNamedArg(int, 'timeout')], Dict[str, Any]],
                       ) -> Dict[str, Any]:
        def partial() -> Dict[str, Any]:
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
                cell = Cell(CellKind.CODE, str(msg['content']['data']), hashid)
                for nb in self.notebooks:
                    nb.add_cell(cell)
            pprint(msg)

    async def _shell_receiver(self) -> None:
        while True:
            try:
                msg = await self._get_msg(self._client.get_shell_msg)
            except queue.Empty:
                continue
            pprint(msg)

    def execute(self, cell: Cell) -> None:
        msg_id = MsgId(self._client.execute(cell.content))
        self._hashids[msg_id] = cell.hashid

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
    def __init__(self, path: str, kernel: Kernel, notebooks: Set[Notebook]) -> None:
        self.path = Path(path)
        self.kernel = kernel
        self.notebooks = notebooks
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
            Cell(kind, con, get_hash(con)) for kind, con in zip(
                cycle([CellKind.TEXT, CellKind.CODE]),
                contents
            )
        ]
        return cells

    async def run(self) -> None:
        self._observer.start()
        while True:
            src = await self.file_change()
            cells = self._parse(src)
            for nb in self.notebooks:
                for cell in cells:
                    nb.add_cell(cell)
                    if cell.kind == CellKind.CODE:
                        self.kernel.execute(cell)


async def neptune(path: str) -> None:
    notebooks: Set[Notebook] = set()
    kernel = Kernel(notebooks)
    source = Source(path, kernel, notebooks)

    async def handler(ws: WebSocket, path: str) -> None:
        nb = Notebook(ws)
        notebooks.add(nb)
        await nb.run()
        notebooks.remove(nb)

    await asyncio.gather(
        websockets.serve(handler, 'localhost', 6060),
        source.run(),
        kernel.run()
    )
