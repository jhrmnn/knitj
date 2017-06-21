# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
import functools
from pprint import pprint, pformat
import queue
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
        self.ws = ws
        print('Got client:', self.ws)
        self._output_queue = Queue()

    async def sender(self):
        while True:
            data = await self._output_queue.get()
            await self.ws.send(data)

    async def receiver(self):
        while True:
            data = await self.ws.recv()
            print(self.ws, data)

    def add_output(self, data):
        self._output_queue.put_nowait(data)

    async def run(self):
        sender = asyncio.ensure_future(self.sender())
        receiver = asyncio.ensure_future(self.receiver())
        (future,), _ = await asyncio.wait(
            [sender, receiver],
            return_when=asyncio.FIRST_COMPLETED,
        )
        try:
            future.result()
        except websockets.ConnectionClosed as e:
            print('Notebook disconnected:', self.ws)
            sender.cancel()
            receiver.cancel()


class Kernel:
    def __init__(self, notebooks):
        self.notebooks = notebooks
        self._kernel = jupyter_client.KernelManager(kernel_name='python3')
        self._kernel.start_kernel()
        self._client = self._kernel.blocking_client()
        self._loop = asyncio.get_event_loop()

    async def _get_msg(self, func):
        return await self._loop.run_in_executor(
            None, functools.partial(func, timeout=1)
        )

    async def iopub_receiver(self):
        while True:
            try:
                msg = await self._get_msg(self._client.get_iopub_msg)
            except queue.Empty:
                continue
            data = pformat(msg)
            for nb in self.notebooks:
                nb.add_output(data)

    async def shell_receiver(self):
        while True:
            try:
                msg = await self._get_msg(self._client.get_shell_msg)
            except queue.Empty:
                continue
            pprint(msg)

    def execute(self, code):
        self._client.execute(code)

    async def run(self):
        try:
            await asyncio.wait(
                [self.iopub_receiver(), self.shell_receiver()],
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            self._client.shutdown()


class Source:
    def __init__(self, kernel, watched):
        self.watched = Path(watched)
        self.kernel = kernel
        self._queue = Queue()
        self._observer = Observer()
        self._observer.schedule(FileChangedHandler(queue=self._queue), '.')
        self._observer.start()

    async def file_change(self):
        while True:
            file = Path(await self._queue.get())
            if file == self.watched:
                return file.read_text()

    async def run(self):
        while True:
            src = await self.file_change()
            self.kernel.execute(src)


async def neptune(watched):
    notebooks = set()
    kernel = Kernel(notebooks)
    source = Source(kernel, watched)

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
