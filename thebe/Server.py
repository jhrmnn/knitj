# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
from itertools import chain
import asyncio
import webbrowser

from aiohttp import web
import ansi2html
from pygments.styles import get_style_by_name
from pygments.formatters import HtmlFormatter
from jinja2 import Template
import websockets

from typing import Callable, Awaitable

WebSocket = websockets.WebSocketServerProtocol


class WebServer:
    def __init__(self, get_html: Callable[[], str],
                 browser: webbrowser.BaseBrowser = None) -> None:
        self.get_html = get_html
        self._root = Path(__file__).parents[1]/'client'
        self._browser = browser

    def _get_response(self, text: str) -> web.Response:
        return web.Response(text=text, content_type='text/html')

    def get_index(self, cells: str = None, client: bool = False) -> str:
        template = Template((self._root/'templates/index.html').read_text())
        return template.render(
            cells=cells or self.get_html(),
            styles='\n'.join(chain(
                [HtmlFormatter(style=get_style_by_name('trac')).get_style_defs()],
                map(str, ansi2html.style.get_styles())
            )),
            client=client,
        )

    async def handler(self, request: web.BaseRequest) -> web.Response:
        if request.path == '/':
            return self._get_response(self.get_index(client=True))
        try:
            text = (self._root/'static'/request.path[1:]).read_text()
        except FileNotFoundError:
            raise web.HTTPNotFound()
        return self._get_response(text)

    async def run(self) -> None:
        server = web.Server(self.handler)
        loop = asyncio.get_event_loop()
        for port in range(8080, 8100):
            try:
                await loop.create_server(server, '127.0.0.1', port)  # type: ignore
            except OSError:
                pass
            else:
                break
        else:
            raise RuntimeError('Cannot find an available port')
        print(f'Started web server on port {port}')
        if self._browser:
            self._browser.open(f'http://localhost:{port}')


class WSServer:
    def __init__(self, handler: Callable[[WebSocket], Awaitable]) -> None:
        self.handler = handler

    async def _handler(self, ws: WebSocket, path: str) -> None:
        await self.handler(ws)

    async def run(self) -> None:
        for port in range(6060, 6080):
            try:
                await websockets.serve(self._handler, 'localhost', port)
            except OSError:
                pass
            else:
                break
        else:
            raise RuntimeError('Cannot find an available port')
        print(f'Started websocket server on port {port}')
