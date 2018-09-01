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
from pkg_resources import resource_string

from aiohttp import web
import ansi2html
import jinja2
from pygments.formatters import HtmlFormatter
from pygments.styles import get_style_by_name

from .kernel import Kernel
from .source import SourceWatcher
from .webserver import init_webapp
from .parser import Parser
from .document import Document
from .cell import Hash, CodeCell
from . import jupyter_messaging as jupy

from typing import Set, Dict, List, Optional, Any, IO, Iterable  # noqa

log = logging.getLogger('knitj')


def render_index(title: str, cells: str, client: bool = True) -> str:
    index = resource_string('knitj', 'client/templates/index.html').decode()
    template = jinja2.Template(index)
    styles = '\n'.join(chain(
        [HtmlFormatter(style=get_style_by_name('trac')).get_style_defs()],
        map(str, ansi2html.style.get_styles())
    ))
    return template.render(title=title, cells=cells, styles=styles, client=client)


async def convert(source: IO[str], output: IO[str], fmt: str,
                  kernel_name: str = None) -> None:
    document = Document(Parser(fmt))
    document.update_from_source(source.read())
    kernel = Kernel(document.process_message, kernel_name)
    kernel.start()
    front, back = render_index('', '__CELLS__', client=False).split('__CELLS__')
    output.write(front)
    for hashid, cell in document.items():
        if isinstance(cell, CodeCell):
            kernel.execute(cell.hashid, cell.code)
    for hashid, cell in document.items():
        if isinstance(cell, CodeCell):
            await cell.wait_for()
        output.write(cell.html)
    output.write(back)
    await kernel.cleanup()


class Broadcaster:
    def __init__(self, wss: Iterable[web.WebSocketResponse]) -> None:
        self._wss = wss
        self._queue: 'asyncio.Queue[Dict]' = asyncio.Queue()

    def register_message(self, msg: Dict) -> None:
        self._queue.put_nowait(msg)

    async def run(self) -> None:
        log.info(f'Started broadcasting to browsers')
        while True:
            msg = await self._queue.get()
            data = json.dumps(msg)
            for ws in self._wss:
                await ws.send_str(data)


class KnitjServer:
    def __init__(self, source: os.PathLike, output: os.PathLike, fmt: str,
                 browser: webbrowser.BaseBrowser = None,
                 kernel: str = None) -> None:
        source, output = Path(source), Path(output)
        self._browser = browser
        self._kernel = Kernel(self._kernel_handler, kernel)
        app = init_webapp(self.get_index, self._ws_msg_handler)
        self._webrunner = web.AppRunner(app)
        self._broadcaster = Broadcaster(app['wss'])
        self._watcher = SourceWatcher(self._source_handler, source)
        self._document = Document(Parser(fmt))
        if source.exists():
            self._document.update_from_source(source.read_text())
        if output.exists():
            self._document.load_output_from_html(output.read_text())
        self._output = output
        self._tasks: List[asyncio.Future] = []

    async def start(self) -> None:
        await self._webrunner.setup()
        self._kernel.start()
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
        self._tasks.extend([
            asyncio.ensure_future(self._broadcaster.run()),
            asyncio.ensure_future(self._watcher.run()),
        ])

    async def cleanup(self) -> None:
        await asyncio.gather(self._webrunner.cleanup(), self._kernel.cleanup())
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def update_all(self, msg: Dict) -> None:
        self._broadcaster.register_message(msg)
        self._output.write_text(self.get_index(client=False))

    def get_index(self, client: bool = True) -> str:
        cells = '\n'.join(cell.html for cell in self._document)
        return render_index('', cells, client=client)

    def _kernel_handler(self, msg: jupy.Message, hashid: Hash) -> None:
        cell = self._document.process_message(msg, hashid)
        if not cell:
            return
        self.update_all(dict(
            kind='cell',
            hashid=cell.hashid,
            html=cell.html,
        ))

    def _ws_msg_handler(self, msg: Dict) -> None:
        if msg['kind'] == 'reevaluate':
            log.info('Will reevaluate a cell')
            hashid = msg['hashid']
            cell = self._document[hashid]
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

    def _source_handler(self, src: str) -> None:
        doc = self._document
        new_cells, updated_cells = doc.update_from_source(src)
        log.info(
            f'File change: {len(new_cells)}/{len(doc)} new cells, '
            f'{len(updated_cells)}/{len(doc)} updated cells'
        )
        for cell in new_cells:
            if isinstance(cell, CodeCell):
                cell._flags.add('evaluating')
        self.update_all(dict(
            kind='document',
            hashids=doc.hashes(),
            htmls={cell.hashid: cell.html for cell in new_cells + updated_cells},
        ))
        for cell in new_cells:
            if isinstance(cell, CodeCell):
                self._kernel.execute(cell.hashid, cell.code)
