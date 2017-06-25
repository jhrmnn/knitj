# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import websockets
import asyncio
from asyncio import Queue
import json

from typing import NewType, TYPE_CHECKING
if TYPE_CHECKING:
    from .neptune import Kernel  # noqa

WebSocket = websockets.WebSocketServerProtocol

Data = NewType('Data', str)


class Notebook:
    def __init__(self, ws: WebSocket, kernel: 'Kernel') -> None:
        print('Got client:', ws)
        self.ws = ws
        self.kernel = kernel
        self._msg_queue: 'Queue[Data]' = Queue()

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
