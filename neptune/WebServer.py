# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
from itertools import chain
import asyncio

from aiohttp import web
import ansi2html
from pygments.formatters import HtmlFormatter
from jinja2 import Template

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .neptune import Neptune  # noqa


class WebServer:
    def __init__(self, neptune: 'Neptune') -> None:
        self._neptune = neptune
        self._root = Path(__file__).parents[1]/'client'

    def _get_response(self, text: str) -> web.Response:
        return web.Response(text=text, content_type='text/html')

    async def handler(self, request: web.BaseRequest) -> web.Response:
        if request.path == '/':
            return self._get_response(
                Template((self._root/'templates/index.html').read_text()).render(
                    cells=self._neptune.html,
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
