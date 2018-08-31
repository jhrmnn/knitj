# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
from itertools import chain
import json
import asyncio
from asyncio import Queue
import webbrowser
import logging

from aiohttp import web
import ansi2html
from pygments.styles import get_style_by_name
from pygments.formatters import HtmlFormatter
from jinja2 import Template

from typing import Callable, Awaitable, Optional, Dict, Set  # noqa

log = logging.getLogger('knitj.server')


class App:
    def __init__(self) -> None:
        self.loop = asyncio.get_event_loop()


class Server:
    def __init__(self, get_html: Callable[[], str],
                 nb_msg_handler: Callable[[Dict], None],
                 browser: webbrowser.BaseBrowser = None) -> None:
        self.get_html = get_html
        self._notebooks: Set[web.WebSocketResponse] = set()
        self._root = Path(__file__).parent/'client'
        self._browser = browser
        self._nb_msg_handler = nb_msg_handler
        self._msg_queue: 'Queue[Dict]' = Queue()

    def _get_response(self, text: str) -> web.Response:
        return web.Response(text=text, content_type='text/html')

    def broadcast(self, msg: Dict) -> None:
        self._msg_queue.put_nowait(msg)

    async def _broadcaster(self) -> None:
        while True:
            msg = await self._msg_queue.get()
            data = json.dumps(msg)
            for ws in self._notebooks:
                await ws.send_str(data)

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
        if request.path == '/ws':
            ws = web.WebSocketResponse(autoclose=False)
            request.app = App()  # type: ignore
            await ws.prepare(request)
            log.info(f'Notebook connected: {id(ws)}')
            self._notebooks.add(ws)
            async for msg in ws:
                self._nb_msg_handler(msg.json())
            log.info(f'Notebook disconnected: {id(ws)}')
            self._notebooks.remove(ws)
            return ws
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
        log.info(f'Started web server on port {port}')
        if self._browser:
            self._browser.open(f'http://localhost:{port}')
        await self._broadcaster()
