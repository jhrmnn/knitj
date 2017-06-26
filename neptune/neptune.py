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

from typing import Set, Dict, List, Optional  # noqa
from .Cell import BaseCell, Hash  # noqa

WebSocket = websockets.WebSocketServerProtocol

_ansi_convert = ansi2html.Ansi2HTMLConverter().convert


class Neptune:
    def __init__(self, path: str) -> None:
        self.path = path
        self._notebooks: Set[Notebook] = set()
        self._kernel = Kernel(self._kernel_handler)
        self._cell_order: List[Hash] = []
        self._cells: Dict[Hash, BaseCell] = {}

    def _nb_msg_handler(self, msg: Dict) -> None:
        if msg['kind'] == 'reevaluate':
            hashid = msg['hashid']
            cell = self._cells[hashid]
            assert isinstance(cell, CodeCell)
            self._kernel.execute(hashid, cell.code)

    async def _nb_handler(self, ws: WebSocket, path: str) -> None:
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

    def _kernel_handler(self, msg: jupy.Message, hashid: Optional[Hash]) -> None:
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
        elif isinstance(msg, jupy.STATUS):
            return
        elif isinstance(msg, jupy.EXECUTE_INPUT):
            return
        elif isinstance(msg, jupy.ERROR):
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

    def _get_html(self) -> str:
        return '\n'.join(self._cells[hashid].html for hashid in self._cell_order)

    async def run(self) -> None:
        await asyncio.gather(
            self._kernel.run(),
            websockets.serve(self._nb_handler, 'localhost', 6060),
            Source(self._source_handler, self.path).run(),
            WebServer(self._get_html).run(),
        )
