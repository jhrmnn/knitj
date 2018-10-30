# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging
from weakref import WeakSet
from pkg_resources import resource_filename

from aiohttp import web, WSCloseCode

from typing import Callable, Dict

log = logging.getLogger('knitj.webserver')


async def on_shutdown(app: web.Application) -> None:
    log.info('Closing websockets')
    ws: web.WebSocketResponse
    for ws in set(app['wss']):
        await ws.close(code=WSCloseCode.GOING_AWAY, message='Server shutdown')


async def handler(request: web.Request) -> web.Response:
    app = request.app
    if request.path == '/':
        return web.Response(text=app['get_index'](), content_type='text/html')
    if request.path == '/ws':
        ws = web.WebSocketResponse(autoclose=False)
        await ws.prepare(request)
        log.info(f'Browser connected: {id(ws)}')
        app['wss'].add(ws)
        async for msg in ws:
            app['ws_msg_handler'](msg.json())
        log.info(f'Browser disconnected: {id(ws)}')
        app['wss'].remove(ws)
        return ws
    raise web.HTTPNotFound()


def init_webapp(
    get_index: Callable[[], str], ws_msg_handler: Callable[[Dict], None]
) -> web.Application:
    app = web.Application()
    app['get_index'] = get_index
    app['ws_msg_handler'] = ws_msg_handler
    app['wss'] = WeakSet()
    app.router.add_static(
        '/static', resource_filename('knitj', 'client/static'), append_version=True
    )
    app.router.add_get('/', handler)
    app.router.add_get('/ws', handler)
    app.on_shutdown.append(on_shutdown)
    return app
