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

    def on_modified(self, event):
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event.src_path)


class Notebook:
    def __init__(self, ws):
        self._ws = ws
        print('Got client:', self._ws)
        self.output_queue = Queue()

    async def sender(self):
        while True:
            data = await self.output_queue.get()
            await self._ws.send(data)

    async def receiver(self):
        while True:
            data = await self._ws.recv()
            print(self._ws, data)

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
            print('Notebook disconnected:', self._ws)
            sender.cancel()
            receiver.cancel()


class Kernel:
    def __init__(self, notebooks):
        self.kernel = jupyter_client.KernelManager(kernel_name='python3')
        self.kernel.start_kernel()
        self.client = self.kernel.blocking_client()
        self.notebooks = notebooks
        self._loop = asyncio.get_event_loop()

    async def get_msg(self, func):
        return await self._loop.run_in_executor(
            None, functools.partial(func, timeout=1)
        )

    async def iopub_receiver(self):
        while True:
            try:
                msg = await self.get_msg(self.client.get_iopub_msg)
            except queue.Empty:
                continue
            data = pformat(msg)
            for nb in self.notebooks:
                nb.output_queue.put_nowait(data)

    async def shell_receiver(self):
        while True:
            try:
                msg = await self.get_msg(self.client.get_shell_msg)
            except queue.Empty:
                continue
            pprint(msg)

    def execute(self, code):
        self.client.execute(code)

    async def run(self):
        try:
            await asyncio.wait(
                [self.iopub_receiver(), self.shell_receiver()],
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            self.client.shutdown()


async def watcher(kernel, watched):
    watched = Path(watched)
    queue = Queue()
    observer = Observer()
    observer.schedule(FileChangedHandler(queue=queue), '.')
    observer.start()
    while True:
        file = Path(await queue.get())
        if file == watched:
            code = file.read_text()
            kernel.execute(code)


async def neptune(watched):
    notebooks = set()
    kernel = Kernel(notebooks)

    async def handler(ws, path):
        nb = Notebook(ws)
        notebooks.add(nb)
        await nb.run()
        notebooks.remove(nb)
    await asyncio.gather(
        websockets.serve(handler, 'localhost', 6060),
        watcher(kernel, watched),
        kernel.run()
    )
