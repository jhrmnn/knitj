# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
from itertools import chain
import asyncio

import ansi2html
import websockets
from aiohttp import web
from pygments.formatters import HtmlFormatter
from jinja2 import Template

from .Notebook import Notebook
from .Renderer import Renderer
from .Kernel import Kernel
from .Source import Source

from typing import Set  # noqa

WebSocket = websockets.WebSocketServerProtocol


class WebServer:
    def __init__(self, renderer: Renderer) -> None:
        self.renderer = renderer
        self._root = Path(__file__).parents[1]/'client'

    def _get_response(self, text: str) -> web.Response:
        return web.Response(text=text, content_type='text/html')

    async def handler(self, request: web.BaseRequest) -> web.Response:
        if request.path == '/':
            return self._get_response(
                Template((self._root/'templates/index.html').read_text()).render(
                    cells=self.renderer.get_last_html(),
                    styles='\n'.join(chain(
                        [HtmlFormatter().get_style_defs()],
                        map(str, ansi2html.style.get_styles())
                    ))
                )
            )
        try:
            text = (self._root/'static'/request.path[1:]).read_text()
        except FileNotFoundError:
            raise web.HTTPNotFound()
        return self._get_response(text)

    async def run(self) -> None:
        server = web.Server(self.handler)
        loop = asyncio.get_event_loop()
        await loop.create_server(server, '127.0.0.1', 8080)  # type: ignore


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
