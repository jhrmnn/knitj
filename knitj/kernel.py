# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import queue
from pprint import pformat
import asyncio
from asyncio import Queue

import jupyter_client

from .cell import Hash
from . import jupyter_messaging as jupy
from .jupyter_messaging import UUID

from typing import Dict, Optional, Callable


class Kernel:
    def __init__(self, handler: Callable[[jupy.Message, Optional[Hash]], None],
                 kernel: str = None, log: Callable[[str], None] = None) -> None:
        self.handler = handler
        self.kernel = kernel or 'python3'
        self._log = log
        self._loop = asyncio.get_event_loop()
        self._hashids: Dict[UUID, Hash] = {}
        self._msg_queue: 'Queue[Dict]' = Queue()
        self._started = asyncio.get_event_loop().create_future()

    async def run(self) -> None:
        self.log('Starting kernel...')
        self._kernel = jupyter_client.KernelManager(kernel_name=self.kernel)
        self._kernel.start_kernel()
        try:
            self._client = self._kernel.client()
            self._started.set_result(None)
            self.log('Kernel started')
            await asyncio.gather(
                self._receiver(),
                self._iopub_receiver(),
                self._shell_receiver()
            )
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self.log('Shutting kernel')
        self._kernel.shutdown_kernel()

    def restart(self) -> None:
        self.log('Restarting kernel')
        self._kernel.restart_kernel()

    def execute(self, hashid: Hash, code: str) -> None:
        msg_id = UUID(self._client.execute(code))
        self._hashids[msg_id] = hashid

    async def wait_for_start(self) -> None:
        await self._started

    def log(self, msg: str) -> None:
        if self._log:
            self._log(msg)

    async def _receiver(self) -> None:
        while True:
            dct = await self._msg_queue.get()
            try:
                msg = jupy.parse(dct)
            except (TypeError, ValueError):
                self.log(pformat(dct))
                raise
            if msg.parent_header:
                hashid: Optional[Hash] = self._hashids.get(msg.parent_header.msg_id)
            else:
                hashid = None
            self.handler(msg, hashid)

    async def _iopub_receiver(self) -> None:
        def partial() -> Dict:
            return self._client.get_iopub_msg(timeout=1)
        while True:
            try:
                dct = await self._loop.run_in_executor(None, partial)
            except queue.Empty:
                continue
            self._msg_queue.put_nowait(dct)

    async def _shell_receiver(self) -> None:
        def partial() -> Dict:
            return self._client.get_shell_msg(timeout=1)
        while True:
            try:
                dct = await self._loop.run_in_executor(None, partial)
            except queue.Empty:
                continue
            self._msg_queue.put_nowait(dct)
