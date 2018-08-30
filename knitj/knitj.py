# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os
from pathlib import Path
import asyncio
import sys
import webbrowser

import ansi2html
from bs4 import BeautifulSoup

from .kernel import Kernel
from .source import Source
from .server import Server
from .parser import Parser
from .cell import CodeCell
from . import jupyter_messaging as jupy
from .jupyter_messaging.content import MIME

from typing import Set, Dict, List, Optional, Any# noqa
from .cell import BaseCell, Hash  # noqa

_ansi_convert = ansi2html.Ansi2HTMLConverter().convert


class KnitJ:
    def __init__(self, source: os.PathLike, report: os.PathLike = None,
                 browser: webbrowser.BaseBrowser = None, quiet: bool = False,
                 kernel: str = None) -> None:
        self.source = Path(source)
        self._report_given = bool(report)
        self.report = Path(report) if report else self.source.with_suffix('.html')
        self.quiet = quiet
        self._kernel = Kernel(self._kernel_handler, kernel, self.log)
        self._server = Server(self._get_html, self._nb_msg_handler, browser=browser)
        self._parser = Parser('python' if self.source.suffix == '.py' else 'markdown')
        self._runner: Optional[asyncio.Future] = None
        if self.source.exists():
            cells = self._parser.parse(self.source.read_text())
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
                if 'done' in cell_tag.attrs['class']:
                    cell.set_done()
                if 'hide' in cell_tag.attrs['class']:
                    cell.flags.add('hide')

    async def run(self) -> None:
        self._runner = asyncio.gather(
            self._kernel.run(),
            self._server.run(),
            Source(self._source_handler, self.source).run(),
        )
        await self._runner

    async def static(self) -> None:
        runner = asyncio.ensure_future(self._kernel.run())
        await self._printer()
        runner.cancel()
        try:
            await runner
        except asyncio.CancelledError:
            pass

    async def cleanup(self) -> None:
        if self._runner:
            self._runner.cancel()
            try:
                await self._runner
            except asyncio.CancelledError:
                pass

    def log(self, o: Any) -> None:
        if not self.quiet:
            print(o)

    def _nb_msg_handler(self, msg: Dict) -> None:
        if msg['kind'] == 'reevaluate':
            self.log('Will reevaluate a cell')
            hashid = msg['hashid']
            cell = self._cells[hashid]
            assert isinstance(cell, CodeCell)
            cell.reset()
            self._kernel.execute(hashid, cell.code)
        elif msg['kind'] == 'restart_kernel':
            self.log('Restarting kernel')
            self._kernel.restart()
        elif msg['kind'] == 'ping':
            pass
        else:
            raise ValueError(f'Unkonwn message: {msg["kind"]}')

    def _broadcast(self, msg: Dict) -> None:
        self._server.broadcast(msg)
        self._save_report()

    def _kernel_handler(self, msg: jupy.Message, hashid: Optional[Hash]) -> None:
        if not hashid:
            return
        try:
            cell = self._cells[hashid]
        except KeyError:
            self.log('Cell does not exist anymore')
            return
        assert isinstance(cell, CodeCell)
        if isinstance(msg, jupy.EXECUTE_RESULT):
            self.log('Got an execution result')
            cell.set_output(msg.content.data)
        elif isinstance(msg, jupy.STREAM):
            cell.append_stream(msg.content.text)
        elif isinstance(msg, jupy.DISPLAY_DATA):
            self.log('Got a picture')
            cell.set_output(msg.content.data)
        elif isinstance(msg, jupy.EXECUTE_REPLY):
            if isinstance(msg.content, jupy.content.ERROR):
                self.log('Got an error execution reply')
                html = _ansi_convert(
                    '\n'.join(msg.content.traceback), full=False
                )
                cell.set_error(html)
            elif isinstance(msg.content, jupy.content.OK):
                self.log('Got an execution reply')
                cell.set_done()
        elif isinstance(msg, jupy.ERROR):
            self.log('Got an error')
            html = _ansi_convert(
                '\n'.join(msg.content.traceback), full=False
            )
            cell.set_error(html)
        elif isinstance(msg, (jupy.STATUS,
                              jupy.EXECUTE_INPUT)):
            return
        else:
            assert False
        self._broadcast(dict(
            kind='cell',
            hashid=cell.hashid,
            html=cell.html,
        ))

    def _source_handler(self, src: str) -> None:
        cells = self._parser.parse(src)
        new_cells = []
        updated_cells: List[BaseCell] = []
        for cell in cells:
            if cell.hashid in self._cells:
                old_cell = self._cells[cell.hashid]
                if isinstance(old_cell, CodeCell):
                    assert isinstance(cell, CodeCell)
                    if old_cell.update_flags(cell):
                        updated_cells.append(old_cell)
            else:
                if isinstance(cell, CodeCell):
                    cell._flags.add('evaluating')
                new_cells.append(cell)
        self.log(
            f'File change: {len(new_cells)}/{len(cells)} new cells, '
            f'{len(updated_cells)}/{len(cells)} updated cells'
        )
        self._cell_order = [cell.hashid for cell in cells]
        self._cells = {
            cell.hashid: self._cells.get(cell.hashid, cell) for cell in cells
        }
        self._broadcast(dict(
            kind='document',
            hashids=self._cell_order,
            htmls={cell.hashid: cell.html for cell in new_cells + updated_cells},
        ))
        for cell in new_cells:
            if isinstance(cell, CodeCell):
                self._kernel.execute(cell.hashid, cell.code)

    def _save_report(self) -> None:
        if self.report:
            self.report.write_text(self._server.get_index())

    def _get_html(self) -> str:
        return '\n'.join(self._cells[hashid].html for hashid in self._cell_order)

    async def _write_to_file(self, f, front, back):
        f.write(front)
        try:
            for hashid in self._cell_order:
                cell = self._cells[hashid]
                if isinstance(cell, CodeCell):
                    await cell.wait_for()
                f.write(cell.html)
        except Exception:
            raise
        else:
            f.write(back)

    async def _printer(self) -> None:
        index = self._server.get_index('__CELLS__')
        front, back = index.split('__CELLS__')
        await self._kernel.wait_for_start()
        for hashid in self._cell_order:
            cell = self._cells[hashid]
            if isinstance(cell, CodeCell):
                self._kernel.execute(cell.hashid, cell.code)
        if self._report_given:
            with self.report.open('w') as f:
                await self._write_to_file(f, front, back)
        else:
            await self._write_to_file(sys.stdout, front, back)
