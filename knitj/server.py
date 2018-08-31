# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
from itertools import chain
import json
from asyncio import Queue
import webbrowser
import logging
from weakref import WeakSet
from pkg_resources import resource_filename

from aiohttp import web, WSCloseCode
import ansi2html
from pygments.styles import get_style_by_name
from pygments.formatters import HtmlFormatter
from jinja2 import Template

from typing import Callable, Awaitable, Optional, Dict, Set  # noqa

log = logging.getLogger('knitj.server')


class Server:
    def __init__(self, get_html: Callable[[], str],
                 nb_msg_handler: Callable[[Dict], None],
                 browser: webbrowser.BaseBrowser = None) -> None:
        self.get_html = get_html
        self._notebooks: 'WeakSet[web.WebSocketResponse]' = WeakSet()
        self._root = Path(__file__).parent/'client'
        self._browser = browser
        self._nb_msg_handler = nb_msg_handler
        self._msg_queue: 'Queue[Dict]' = Queue()
        self._app = web.Application()
        self._app.router.add_static('/static', resource_filename('knitj', 'client/static'))
        self._app.router.add_get('/', self.handler)
        self._app.router.add_get('/ws', self.handler)
        self._app.on_shutdown.append(self._on_shutdown)
        self._runner = web.AppRunner(self._app)

    async def _on_shutdown(self, app):
        for ws in set(self._notebooks):
            await ws.close(code=WSCloseCode.GOING_AWAY, message='Server shutdown')

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

    async def handler(self, request: web.Request) -> web.Response:
        if request.path == '/':
            return self._get_response(self.get_index(client=True))
        if request.path == '/ws':
            ws = web.WebSocketResponse(autoclose=False)
            await ws.prepare(request)
            log.info(f'Notebook connected: {id(ws)}')
            self._notebooks.add(ws)
            async for msg in ws:
                self._nb_msg_handler(msg.json())
            log.info(f'Notebook disconnected: {id(ws)}')
            self._notebooks.remove(ws)
            return ws
        raise web.HTTPNotFound()

    async def run(self) -> None:
        await self._runner.setup()
        for port in range(8080, 8100):
            try:
                site = web.TCPSite(self._runner, 'localhost', port)
                await site.start()
            except OSError:
                pass
            else:
                break
        else:
            raise RuntimeError('No available port')
        log.info(f'Started web server on port {port}')
        if self._browser:
            self._browser.open(f'http://localhost:{port}')
        await self._broadcaster()
