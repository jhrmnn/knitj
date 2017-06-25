# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio

import websockets

from .Notebook import Notebook
from .Renderer import Renderer
from .Kernel import Kernel
from .Source import Source
from .WebServer import WebServer

from typing import Set  # noqa

WebSocket = websockets.WebSocketServerProtocol


async def neptune(path: str) -> None:
    notebooks: Set[Notebook] = set()
    renderer = Renderer(notebooks)
    kernel = Kernel(renderer)
    source = Source(path, kernel, renderer)
    webserver = WebServer(renderer)

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
        webserver.run(),
    )
