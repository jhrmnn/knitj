# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
import functools
from pprint import pprint, pformat
import queue
from collections import namedtuple
from itertools import cycle
import hashlib
from enum import Enum
import asyncio
from asyncio import Queue

import websockets
import jupyter_client
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class FileChangedHandler(FileSystemEventHandler):
    def __init__(self, *args, queue, **kwargs):
        super().__init__(*args, **kwargs)
        self._loop = asyncio.get_event_loop()
        self._queue = queue

    def _queue_modified(self, event):
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event.src_path)

    def on_modified(self, event):
        self._queue_modified(event)

    def on_created(self, event):
        self._queue_modified(event)


class Notebook:
    def __init__(self, ws):
        print('Got client:', ws)
        self.ws = ws
        self._output_queue = Queue()

    async def _sender(self):
        while True:
            data = await self._output_queue.get()
            await self.ws.send(data)

    async def _receiver(self):
        while True:
            data = await self.ws.recv()
            print(self.ws, data)

    def add_output(self, data):
        self._output_queue.put_nowait(data)

    async def run(self):
        try:
            await asyncio.gather(self._sender(), self._receiver())
        except websockets.ConnectionClosed as e:
            print('Notebook disconnected:', self.ws)


class Kernel:
    def __init__(self, notebooks):
        self.notebooks = notebooks
        self._loop = asyncio.get_event_loop()
        self._hashids = {}

    async def _get_msg(self, func):
        return await self._loop.run_in_executor(
            None, functools.partial(func, timeout=1)
        )

    async def _iopub_receiver(self):
        while True:
            try:
                msg = await self._get_msg(self._client.get_iopub_msg)
            except queue.Empty:
                continue
            if msg['msg_type'] == 'execute_result':
                hashid = self._hashids[msg['parent_header']['msg_id']]
                data = pformat((hashid, msg['content']['data']))
                for nb in self.notebooks:
                    nb.add_output(data)
            pprint(msg)

    async def _shell_receiver(self):
        while True:
            try:
                msg = await self._get_msg(self._client.get_shell_msg)
            except queue.Empty:
                continue
            pprint(msg)

    def execute(self, cell):
        msg_id = self._client.execute(cell.content)
        self._hashids[msg_id] = cell.hashid

    async def run(self):
        kernel = jupyter_client.KernelManager(kernel_name='python3')
        try:
            kernel.start_kernel()
            self._client = kernel.client()
            await asyncio.gather(self._iopub_receiver(), self._shell_receiver())
        finally:
            self._client.shutdown()


def get_hash(s):
    return hashlib.sha1(s.encode()).hexdigest()


class CellKind(Enum):
    TEXT = 0
    CODE = 1


Cell = namedtuple('Cell', 'kind content hashid')


class Source:
    def __init__(self, path, kernel, notebooks):
        self.path = Path(path)
        self.kernel = kernel
        self.notebooks = notebooks
        self._queue = Queue()
        self._observer = Observer()
        self._observer.schedule(FileChangedHandler(queue=self._queue), '.')

    async def file_change(self):
        while True:
            file = Path(await self._queue.get())
            if file == self.path:
                return file.read_text()

    def _parse(self, src):
        contents = src.split('```')
        assert len(contents) % 2 == 1
        cells = [
            Cell(kind, con, get_hash(con)) for kind, con in zip(
                cycle([CellKind.TEXT, CellKind.CODE]),
                contents
            )
        ]
        return cells

    async def run(self):
        self._observer.start()
        while True:
            src = await self.file_change()
            cells = self._parse(src)
            for nb in self.notebooks:
                for cell in cells:
                    nb.add_output(pformat(cell))
                    if cell.kind == CellKind.CODE:
                        self.kernel.execute(cell)


async def neptune(path):
    notebooks = set()
    kernel = Kernel(notebooks)
    source = Source(path, kernel, notebooks)

    async def handler(ws, path):
        nb = Notebook(ws)
        notebooks.add(nb)
        await nb.run()
        notebooks.remove(nb)

    await asyncio.gather(
        websockets.serve(handler, 'localhost', 6060),
        source.run(),
        kernel.run()
    )
