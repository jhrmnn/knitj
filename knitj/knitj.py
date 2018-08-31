# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os
from pathlib import Path
import asyncio
import webbrowser
import json
import logging
from itertools import chain
# from collections import OrderedDict
from pkg_resources import resource_string

from aiohttp import web
import ansi2html
from jinja2 import Template
from pygments.formatters import HtmlFormatter
from pygments.styles import get_style_by_name

from .kernel import Kernel
from .source import Source
from .webserver import init_webapp
from .parser import Parser
from .cell import CodeCell
from .document import Document

from typing import Set, Dict, List, Optional, Any, IO, Iterable  # noqa
from .cell import BaseCell, Hash  # noqa
from . import jupyter_messaging as jupy

log = logging.getLogger('knitj')


def render_index(cells: str, client: bool = True) -> str:
    index = resource_string('knitj', 'client/templates/index.html').decode()
    template = Template(index)
    return template.render(
        cells=cells,
        styles='\n'.join(chain(
            [HtmlFormatter(style=get_style_by_name('trac')).get_style_defs()],
            map(str, ansi2html.style.get_styles())
        )),
        client=client,
    )


async def convert(source: IO[str], output: IO[str], fmt: str,
                  kernel_name: str = None) -> None:
    front, back = render_index('__CELLS__', client=False).split('__CELLS__')
    output.write(front)
    parser = Parser(fmt)
    cells = parser.parse(source.read())
    document = Document(cells)
    kernel = Kernel(document.process_message, kernel_name)
    runner = asyncio.ensure_future(kernel.run())
    await kernel.wait_for_start()
    for hashid, cell in document.cells.items():
        if isinstance(cell, CodeCell):
            kernel.execute(cell.hashid, cell.code)
    for hashid, cell in document.cells.items():
        if isinstance(cell, CodeCell):
            await cell.wait_for()
        output.write(cell.html)
    output.write(back)
    runner.cancel()
    try:
        await runner
    except asyncio.CancelledError:
        pass


class Broadcaster:
    def __init__(self, wss: Iterable[web.WebSocketResponse]) -> None:
        self._wss = wss
        self._queue: 'asyncio.Queue[Dict]' = asyncio.Queue()

    def broadcast(self, msg: Dict) -> None:
        self._queue.put_nowait(msg)

    async def run(self) -> None:
        while True:
            msg = await self._queue.get()
            data = json.dumps(msg)
            for ws in self._wss:
                await ws.send_str(data)


class KnitjServer:
    def __init__(self, source: os.PathLike, output: os.PathLike, fmt: str,
                 browser: webbrowser.BaseBrowser = None,
                 kernel: str = None) -> None:
        self.source = Path(source)
        self.output = Path(output)
        self._browser = browser
        self._kernel = Kernel(self._kernel_handler, kernel)
        self._webapp = init_webapp(self._get_index, self._nb_msg_handler)
        self._webrunner = web.AppRunner(self._webapp)
        self._parser = Parser(fmt)
        self._runners: List[asyncio.Future] = []
        self._broadcaster = Broadcaster(self._webapp['nb_wss'])
        if self.source.exists():
            cells = self._parser.parse(self.source.read_text())
        else:
            cells = []
        self._document = Document(cells)
        if self.output.exists():
            self._document.load_output_from_html(self.output.read_text())

    async def start(self) -> None:
        await self._webrunner.setup()
        for port in range(8080, 8100):
            try:
                site = web.TCPSite(self._webrunner, 'localhost', port)
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
        self._runners.extend([
            asyncio.ensure_future(self._kernel.run()),
            asyncio.ensure_future(self._broadcaster.run()),
            asyncio.ensure_future(Source(self._source_handler, self.source).run()),
        ])

    def _kernel_handler(self, msg: jupy.Message, hashid: Hash) -> None:
        cell = self._document.process_message(msg, hashid)
        if not cell:
            return
        self._broadcast(dict(
            kind='cell',
            hashid=cell.hashid,
            html=cell.html,
        ))

    async def cleanup(self) -> None:
        await self._webrunner.cleanup()
        for runner in self._runners:
            runner.cancel()
            try:
                await runner
            except asyncio.CancelledError:
                pass

    def _nb_msg_handler(self, msg: Dict) -> None:
        if msg['kind'] == 'reevaluate':
            log.info('Will reevaluate a cell')
            hashid = msg['hashid']
            cell = self._document.cells[hashid]
            assert isinstance(cell, CodeCell)
            cell.reset()
            self._kernel.execute(hashid, cell.code)
        elif msg['kind'] == 'restart_kernel':
            log.info('Restarting kernel')
            self._kernel.restart()
        elif msg['kind'] == 'ping':
            pass
        else:
            raise ValueError(f'Unkonwn message: {msg["kind"]}')

    def _broadcast(self, msg: Dict) -> None:
        self._broadcaster.broadcast(msg)
        self.output.write_text(self._get_index(client=False))

    def _source_handler(self, src: str) -> None:
        cells = self._parser.parse(src)
        new_cells, updated_cells = self._document.update_from_cells(cells)
        log.info(
            f'File change: {len(new_cells)}/{len(cells)} new cells, '
            f'{len(updated_cells)}/{len(cells)} updated cells'
        )
        self._broadcast(dict(
            kind='document',
            hashids=list(self._document.cells),
            htmls={cell.hashid: cell.html for cell in new_cells + updated_cells},
        ))
        for cell in new_cells:
            if isinstance(cell, CodeCell):
                self._kernel.execute(cell.hashid, cell.code)

    def _get_index(self, client: bool = True) -> str:
        cells = '\n'.join(cell.html for cell in self._document.cells.values())
        return render_index(cells, client=client)
