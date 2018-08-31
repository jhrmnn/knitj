# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging
from weakref import WeakSet
from pkg_resources import resource_filename

from aiohttp import web, WSCloseCode

from typing import Callable, Awaitable, Optional, Dict, Set  # noqa

log = logging.getLogger('knitj.webserver')


async def on_shutdown(app: web.Application) -> None:
    ws: web.WebSocketResponse
    for ws in set(app['nb_wss']):
        await ws.close(code=WSCloseCode.GOING_AWAY, message='Server shutdown')


async def handler(request: web.Request) -> web.Response:
    app = request.app
    if request.path == '/':
        return web.Response(text=app['get_index'](), content_type='text/html')
    if request.path == '/ws':
        ws = web.WebSocketResponse(autoclose=False)
        await ws.prepare(request)
        log.info(f'Notebook connected: {id(ws)}')
        app['nb_wss'].add(ws)
        async for msg in ws:
            app['nb_msg_handler'](msg.json())
        log.info(f'Notebook disconnected: {id(ws)}')
        app['nb_wss'].remove(ws)
        return ws
    raise web.HTTPNotFound()


def init_webapp(get_index: Callable[[], str],
                nb_msg_handler: Callable[[Dict], None]) -> web.Application:
        app = web.Application()
        app['get_index'] = get_index
        app['nb_msg_handler'] = nb_msg_handler
        app['nb_wss'] = WeakSet()
        app.router.add_static('/static', resource_filename('knitj', 'client/static'))
        app.router.add_get('/', handler)
        app.router.add_get('/ws', handler)
        app.on_shutdown.append(on_shutdown)
        return app
