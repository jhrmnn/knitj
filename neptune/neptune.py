# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import asyncio

import ansi2html
import websockets

from .Notebook import Notebook
from .Kernel import Kernel
from .Source import Source
from .WebServer import WebServer
from .Parser import Parser
from .Cell import CodeCell
from . import jupyter_messaging as jupy
from .jupyter_messaging.content import MIME

from typing import Set, Dict, List  # noqa
from .Cell import BaseCell, Hash  # noqa

WebSocket = websockets.WebSocketServerProtocol

_ansi_convert = ansi2html.Ansi2HTMLConverter().convert


class Neptune:
    def __init__(self, path: str) -> None:
        self._notebooks: Set[Notebook] = set()
        self._kernel = Kernel()
        self._source = Source(path)
        self._webserver = WebServer(self)
        self._cell_order: List[Hash] = []
        self._cells: Dict[Hash, BaseCell] = {}

    async def _nb_receiver(self, notebook: Notebook) -> None:
        while True:
            msg = await notebook.get_msg()
            if msg['kind'] == 'reevaluate':
                hashid = msg['hashid']
                cell = self._cells[hashid]
                assert isinstance(cell, CodeCell)
                self._kernel.execute(hashid, cell.code)

    async def _nb_handler(self, ws: WebSocket, path: str) -> None:
        print('Got client:', ws)
        nb = Notebook(ws)
        self._notebooks.add(nb)
        try:
            await asyncio.gather(nb.run(), self._nb_receiver(nb))
        except websockets.ConnectionClosed as e:
            print('Notebook disconnected:', ws)
        self._notebooks.remove(nb)

    def _broadcast(self, msg: Dict) -> None:
        for nb in self._notebooks:
            nb.queue_msg(msg)

    async def _kernel_receiver(self) -> None:
        while True:
            msg, hashid = await self._kernel.get_msg()
            print(msg)
            if not hashid:
                continue
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
            elif isinstance(msg, jupy.STATUS):
                continue
            elif isinstance(msg, jupy.EXECUTE_INPUT):
                continue
            elif isinstance(msg, jupy.ERROR):
                continue
            else:
                assert False
            self._broadcast(dict(
                kind='cell',
                hashid=cell.hashid,
                html=cell.html,
            ))

    async def _source_receiver(self) -> None:
        async for src in self._source:
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

    @property
    def html(self) -> str:
        return '\n'.join(self._cells[hashid].html for hashid in self._cell_order)

    async def run(self) -> None:
        await asyncio.gather(
            websockets.serve(self._nb_handler, 'localhost', 6060),
            self._source_receiver(),
            self._kernel.run(),
            self._kernel_receiver(),
            self._webserver.run(),
        )
