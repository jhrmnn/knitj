# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os
from pathlib import Path
import asyncio
import sys
import webbrowser

import ansi2html
import websockets
from bs4 import BeautifulSoup

from .Notebook import Notebook
from .Kernel import Kernel
from .Source import Source
from .Server import WebServer, WSServer
from .Parser import Parser
from .Cell import CodeCell
from . import jupyter_messaging as jupy
from .jupyter_messaging.content import MIME

from typing import Set, Dict, List, Optional  # noqa
from .Cell import BaseCell, Hash  # noqa

WebSocket = websockets.WebSocketServerProtocol

_ansi_convert = ansi2html.Ansi2HTMLConverter().convert


class Thebe:
    def __init__(self, source: os.PathLike, report: os.PathLike = None,
                 browser: webbrowser.BaseBrowser = None, quiet: bool = False) -> None:
        self.source = Path(source)
        self.report = Path(report) if report else None
        self.quiet = quiet
        self._notebooks: Set[Notebook] = set()
        self._kernel = Kernel(self._kernel_handler)
        self._webserver = WebServer(self._get_html, browser=browser)
        if self.source.exists():
            cells = Parser().parse(self.source.read_text())
        else:
            cells = []
        self._cell_order = [cell.hashid for cell in cells]
        self._cells = {cell.hashid: cell for cell in cells}
        if not self.report or not self.report.exists():
            return
        soup = BeautifulSoup(self.report.read_text(), 'html.parser')
        cells_tag = soup.find(id='cells')
        if not cells_tag:
            return
        for cell_tag in cells_tag.find_all('div', class_='code-cell'):
            if cell_tag.attrs['class'][0] in self._cells:
                cell = self._cells[Hash(cell_tag.attrs['class'][0])]
                assert isinstance(cell, CodeCell)
                cell.set_output({
                    MIME.TEXT_HTML: str(cell_tag.find(class_='output'))
                })

    def _nb_msg_handler(self, msg: Dict) -> None:
        if msg['kind'] == 'reevaluate':
            hashid = msg['hashid']
            cell = self._cells[hashid]
            assert isinstance(cell, CodeCell)
            cell.set_output(None)
            self._kernel.execute(hashid, cell.code)
        elif msg['kind'] == 'ping':
            pass
        else:
            raise ValueError(f'Unkonwn message: {msg["kind"]}')

    async def _nb_handler(self, ws: WebSocket) -> None:
        print('Got client:', ws)
        nb = Notebook(ws, self._nb_msg_handler)
        self._notebooks.add(nb)
        try:
            await nb.run()
        except websockets.ConnectionClosed as e:
            print('Notebook disconnected:', ws)
        self._notebooks.remove(nb)

    def _broadcast(self, msg: Dict) -> None:
        for nb in self._notebooks:
            nb.queue_msg(msg)
        self._save_report()

    def _kernel_handler(self, msg: jupy.Message, hashid: Optional[Hash]) -> None:
        if not self.quiet:
            print(msg)
        if not hashid:
            return
        cell = self._cells[hashid]
        assert isinstance(cell, CodeCell)
        if isinstance(msg, jupy.EXECUTE_RESULT):
            cell.set_output(msg.content.data)
        elif isinstance(msg, jupy.STREAM):
            cell.append_stream(msg.content.text)
        elif isinstance(msg, jupy.DISPLAY_DATA):
            cell.set_output(msg.content.data)
        elif isinstance(msg, jupy.EXECUTE_REPLY):
            if isinstance(msg.content, jupy.content.ERROR):
                html = _ansi_convert(
                    '\n'.join(msg.content.traceback), full=False
                )
                cell.set_output({MIME.TEXT_HTML: f'<pre>{html}</pre>'})
            elif isinstance(msg.content, jupy.content.OK):
                cell.set_done()
        elif isinstance(msg, (jupy.STATUS, jupy.EXECUTE_INPUT, jupy.ERROR)):
            return
        else:
            assert False
        self._broadcast(dict(
            kind='cell',
            hashid=cell.hashid,
            html=cell.html,
        ))

    def _source_handler(self, src: str) -> None:
        cells = Parser().parse(src)
        new_cells = [cell for cell in cells if cell.hashid not in self._cells]
        self._cell_order = [cell.hashid for cell in cells]
        self._cells = {
            cell.hashid: self._cells.get(cell.hashid, cell) for cell in cells
        }
        for cell in new_cells:
            if isinstance(cell, CodeCell):
                self._kernel.execute(cell.hashid, cell.code)
        self._broadcast(dict(
            kind='document',
            hashids=self._cell_order,
            htmls={cell.hashid: cell.html for cell in new_cells},
        ))

    def _save_report(self) -> None:
        if self.report:
            self.report.write_text(self._webserver.get_index())

    def _get_html(self) -> str:
        return '\n'.join(self._cells[hashid].html for hashid in self._cell_order)

    async def _printer(self) -> None:
        index = self._webserver.get_index('__CELLS__')
        front, back = index.split('__CELLS__')
        await self._kernel.wait_for_start()
        for hashid in self._cell_order:
            cell = self._cells[hashid]
            if isinstance(cell, CodeCell):
                self._kernel.execute(cell.hashid, cell.code)
        f = self.report.open('w') if self.report else sys.stdout
        f.write(front)
        try:
            for hashid in self._cell_order:
                cell = self._cells[hashid]
                if isinstance(cell, CodeCell):
                    await cell.wait_for()
                f.write(cell.html)
        except:
            raise
        else:
            f.write(back)
        finally:
            if self.report:
                f.close()
        raise AllProcessed

    async def run(self) -> None:
        ws_port = await WSServer(self._nb_handler).run()
        await asyncio.gather(
            self._kernel.run(),
            self._webserver.run(ws_port),
            Source(self._source_handler, self.source).run(),
        )

    async def static(self) -> None:
        try:
            await asyncio.gather(self._kernel.run(), self._printer())
        except AllProcessed:
            self._kernel._client.shutdown()


class AllProcessed(Exception):
    pass
