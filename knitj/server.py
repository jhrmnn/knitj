# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging
from weakref import WeakSet
from pkg_resources import resource_filename

from aiohttp import web, WSCloseCode

from typing import Callable, Awaitable, Optional, Dict, Set  # noqa

log = logging.getLogger('knitj.server')


class Server:
    def __init__(self, get_index: Callable[[], str],
                 nb_msg_handler: Callable[[Dict], None]) -> None:
        self.get_index = get_index
        self._notebooks: 'WeakSet[web.WebSocketResponse]' = WeakSet()
        self._nb_msg_handler = nb_msg_handler
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

    async def handler(self, request: web.Request) -> web.Response:
        if request.path == '/':
            return self._get_response(self.get_index())
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

    async def start(self) -> int:
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
        return port
