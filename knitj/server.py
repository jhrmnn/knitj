# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os
from pathlib import Path
import asyncio
import webbrowser
import json
import logging

from aiohttp import web

from .kernel import Kernel
from .source import SourceWatcher
from .webserver import init_webapp
from .parser import Parser
from .document import Document
from .cell import Hash, CodeCell
from .convert import render_index
from . import jupyter_messaging as jupy

from typing import Set, Dict, List, Optional

log = logging.getLogger('knitj.knitj')


class Broadcaster:
    def __init__(self, wss: Set[web.WebSocketResponse]) -> None:
        self._wss = wss
        self._queue: 'asyncio.Queue[Dict]' = asyncio.Queue()

    def register_message(self, msg: Dict) -> None:
        self._queue.put_nowait(msg)

    async def run(self) -> None:
        log.info(f'Started broadcasting to browsers')
        while True:
            msg = await self._queue.get()
            data = json.dumps(msg)
            for ws in list(self._wss):
                try:
                    await ws.send_str(data)
                except ConnectionResetError:
                    self._wss.remove(ws)


class KnitjServer:
    def __init__(
        self,
        source: os.PathLike,
        output: os.PathLike,
        fmt: str,
        browser: webbrowser.BaseBrowser = None,
        kernel: str = None,
    ) -> None:
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
        loop = asyncio.get_event_loop()
        self._tasks.extend(
            [
                loop.create_task(self._broadcaster.run()),
                loop.create_task(self._watcher.run()),
            ]
        )

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
        try:
            template: Optional[Path] = Path(self._document.frontmatter['template'])
        except KeyError:
            template = None
        return render_index('', cells, client=client, template=template)

    def _kernel_handler(self, msg: jupy.Message, hashid: Optional[Hash]) -> None:
        if not hashid:
            if isinstance(msg, jupy.STATUS):
                if msg.content.execution_state == jupy.content.State.STARTING:
                    self._broadcaster.register_message({'kind': 'kernel_starting'})
            elif isinstance(msg, jupy.SHUTDOWN_REPLY):
                pass
            else:
                log.warn("Don't have parent message")
                log.info(msg)
            return
        cell = self._document.process_message(msg, hashid)
        if not cell:
            return
        self.update_all(
            {'kind': 'cell', 'hashid': cell.hashid.value, 'html': cell.html}
        )

    def _ws_msg_handler(self, msg: Dict) -> None:
        if msg['kind'] == 'reevaluate':
            hashids = [Hash(hashid) for hashid in msg['hashids']]
            log.info(f'Will reevaluate cells: {", ".join(map(str, hashids))}')
            for hashid in hashids:
                cell = self._document[hashid]
                assert isinstance(cell, CodeCell)
                cell.reset()
                self._kernel.execute(hashid, cell.code)
        elif msg['kind'] == 'restart_kernel':
            self._kernel.restart()
        elif msg['kind'] == 'interrupt_kernel':
            self._kernel.interrupt()
        elif msg['kind'] == 'ping':
            pass
        else:
            raise ValueError(f'Unkonwn message: {msg["kind"]}')

    def _source_handler(self, src: str) -> None:
        doc = self._document
        new_cells, updated_cells = doc.update_from_source(src)
        for cell in new_cells:
            if isinstance(cell, CodeCell):
                cell._flags.add('evaluating')
        self.update_all(
            {
                'kind': 'document',
                'hashids': [hashid.value for hashid in doc.hashes()],
                'htmls': {cell.hashid.value: cell.html for cell in updated_cells},
            }
        )
        for cell in new_cells:
            if isinstance(cell, CodeCell):
                self._kernel.execute(cell.hashid, cell.code)
