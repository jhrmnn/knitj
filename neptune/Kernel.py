# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import queue
from pprint import pprint
import asyncio
from asyncio import Queue

import jupyter_client
import ansi2html

from .Renderer import Renderer
from .Cell import Cell, Hash
from . import jupyter_messaging as jupy
from .jupyter_messaging import UUID
from .jupyter_messaging.content import MIME

from typing import Dict


class Kernel:
    def __init__(self, renderer: Renderer) -> None:
        self.renderer = renderer
        self._loop = asyncio.get_event_loop()
        self._hashids: Dict[UUID, Hash] = {}
        self._input_cells: Dict[Hash, Cell] = {}
        self._conv = ansi2html.Ansi2HTMLConverter()
        self._msg_queue: 'Queue[Dict]' = Queue()

    async def _iopub_receiver(self) -> None:
        def partial() -> Dict:
            return self._client.get_iopub_msg(timeout=1)  # type: ignore
        while True:
            try:
                dct = await self._loop.run_in_executor(None, partial)
            except queue.Empty:
                continue
            self._msg_queue.put_nowait(dct)

    async def _shell_receiver(self) -> None:
        def partial() -> Dict:
            return self._client.get_shell_msg(timeout=1)  # type: ignore
        while True:
            try:
                dct = await self._loop.run_in_executor(None, partial)
            except queue.Empty:
                continue
            self._msg_queue.put_nowait(dct)

    def _get_parent(self, msg: jupy.Message) -> Hash:
        assert msg.parent_header
        return self._hashids[msg.parent_header.msg_id]

    async def _msg_handler(self) -> None:
        while True:
            dct = await self._msg_queue.get()
            try:
                msg = jupy.parse(dct)
            except (TypeError, ValueError):
                pprint(dct)
                raise
            print(msg)
            if isinstance(msg, jupy.EXECUTE_RESULT):
                hashid = self._get_parent(msg)
                cell = Cell(Cell.Kind.OUTPUT, msg.content.data, hashid)
                self.renderer.add_task(cell)
            elif isinstance(msg, jupy.STREAM):
                hashid = self._get_parent(msg)
                cell = Cell(
                    Cell.Kind.OUTPUT,
                    {MIME.TEXT_PLAIN: msg.content.text.strip()},
                    hashid
                )
                self.renderer.add_task(cell)
            elif isinstance(msg, jupy.DISPLAY_DATA):
                hashid = self._get_parent(msg)
                cell = Cell(Cell.Kind.OUTPUT, msg.content.data, hashid)
                self.renderer.add_task(cell)
            elif isinstance(msg, jupy.EXECUTE_REPLY):
                hashid = self._get_parent(msg)
                if isinstance(msg.content, jupy.content.ERROR):
                    cell = Cell(
                        Cell.Kind.OUTPUT,
                        {MIME.TEXT_HTML: self._conv.convert(
                            '\n'.join(msg.content.traceback), full=False
                        )},
                        hashid
                    )
                    self.renderer.add_task(cell)

    def execute(self, cell: Cell) -> None:
        assert cell.kind == Cell.Kind.INPUT
        msg_id = UUID(self._client.execute(cell.content[MIME.TEXT_PYTHON]))
        self._input_cells[cell.hashid] = cell
        self._hashids[msg_id] = cell.hashid

    def execute_hashid(self, hashid: Hash) -> None:
        self.execute(self._input_cells.pop(hashid))

    async def run(self) -> None:
        kernel = jupyter_client.KernelManager(kernel_name='python3')
        try:
            kernel.start_kernel()
            self._client = kernel.client()
            await asyncio.gather(
                self._msg_handler(),
                self._iopub_receiver(),
                self._shell_receiver()
            )
        finally:
            self._client.shutdown()
