# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import json
import asyncio
from asyncio import Queue

import websockets

from typing import Dict, Callable

WebSocket = websockets.WebSocketServerProtocol


class Notebook:
    def __init__(self, ws: WebSocket, handler: Callable[[Dict], None]) -> None:
        self.ws = ws
        self.handler = handler
        self._msg_queue: 'Queue[Dict]' = Queue()

    async def _receiver(self) -> None:
        while True:
            data = await self.ws.recv()
            msg: Dict = json.loads(data)
            print(f'{self.ws} got message: {msg}')
            self.handler(msg)

    def queue_msg(self, msg: Dict) -> None:
        self._msg_queue.put_nowait(msg)

    async def _sender(self) -> None:
        while True:
            msg = await self._msg_queue.get()
            await self.ws.send(json.dumps(msg))

    async def run(self) -> None:
        await asyncio.gather(self._receiver(), self._sender())
