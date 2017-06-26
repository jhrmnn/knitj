# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import queue
from pprint import pprint
import asyncio
from asyncio import Queue

import jupyter_client

from .Cell import Hash
from . import jupyter_messaging as jupy
from .jupyter_messaging import UUID

from typing import Dict, Optional, Tuple


class Kernel:
    def __init__(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._hashids: Dict[UUID, Hash] = {}
        self._inputs: Dict[Hash, str] = {}
        self._msg_queue: 'Queue[Dict]' = Queue()

    async def get_msg(self) -> Tuple[jupy.Message, Optional[Hash]]:
        dct = await self._msg_queue.get()
        try:
            msg = jupy.parse(dct)
        except (TypeError, ValueError):
            pprint(dct)
            raise
        if msg.parent_header:
            return msg, self._hashids[msg.parent_header.msg_id]
        return msg, None

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

    def execute(self, hashid: Hash, code: str) -> None:
        msg_id = UUID(self._client.execute(code))
        self._hashids[msg_id] = hashid

    async def run(self) -> None:
        kernel = jupyter_client.KernelManager(kernel_name='python3')
        try:
            kernel.start_kernel()
            self._client = kernel.client()
            await asyncio.gather(self._iopub_receiver(), self._shell_receiver())
        finally:
            self._client.shutdown()
