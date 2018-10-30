# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio
import logging
from pprint import pformat
import queue

import jupyter_client

from .cell import Hash
from . import jupyter_messaging as jupy
from .jupyter_messaging import UUID

from typing import Dict, Callable, Optional

log = logging.getLogger('knitj.kernel')


class Kernel:
    def __init__(
        self,
        handler: Callable[[jupy.Message, Optional[Hash]], object],
        kernel: str = None,
    ) -> None:
        self._handler = handler
        self._kernel_name = kernel or 'python3'
        self._hashids: Dict[UUID, Hash] = {}
        self._msg_queue: 'asyncio.Queue[Dict]' = asyncio.Queue()
        self._loop = asyncio.get_event_loop()

    def start(self) -> None:
        log.info('Starting kernel...')
        self._kernel = jupyter_client.KernelManager(kernel_name=self._kernel_name)
        self._kernel.start_kernel()
        self._client = self._kernel.client()
        log.info('Kernel started')
        self._channels = asyncio.gather(
            self._receiver(), self._iopub_receiver(), self._shell_receiver()
        )

    async def cleanup(self) -> None:
        self._kernel.shutdown_kernel()
        self._channels.cancel()
        try:
            await self._channels
        except asyncio.CancelledError:
            pass
        log.info('Kernel shut down')

    def restart(self) -> None:
        log.info('Restarting kernel')
        self._kernel.restart_kernel()

    def interrupt(self) -> None:
        log.info('Interrupting kernel')
        self._kernel.interrupt_kernel()

    def execute(self, hashid: Hash, code: str) -> None:
        msg_id = UUID(self._client.execute(code))
        self._hashids[msg_id] = hashid

    async def _receiver(self) -> None:
        while True:
            dct = await self._msg_queue.get()
            try:
                msg = jupy.parse(dct)
            except (TypeError, ValueError):
                log.info(pformat(dct))
                raise
            if msg.parent_header:
                hashid = self._hashids.get(msg.parent_header.msg_id)
            else:
                hashid = None
            self._handler(msg, hashid)

    async def _iopub_receiver(self) -> None:
        def partial() -> Dict:
            return self._client.get_iopub_msg(timeout=0.3)

        while True:
            try:
                dct = await self._loop.run_in_executor(None, partial)
            except queue.Empty:
                continue
            self._msg_queue.put_nowait(dct)

    async def _shell_receiver(self) -> None:
        def partial() -> Dict:
            return self._client.get_shell_msg(timeout=0.3)

        while True:
            try:
                dct = await self._loop.run_in_executor(None, partial)
            except queue.Empty:
                continue
            self._msg_queue.put_nowait(dct)
