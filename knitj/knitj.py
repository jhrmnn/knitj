# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os
from pathlib import Path
import asyncio
import sys
import webbrowser
import logging
from itertools import chain
# from collections import OrderedDict
from pkg_resources import resource_string

import ansi2html
from jinja2 import Template
from pygments.formatters import HtmlFormatter
from pygments.styles import get_style_by_name

from .kernel import Kernel
from .source import Source
from .server import Server
from .parser import Parser
from .cell import CodeCell
from .document import Document

from typing import Set, Dict, List, Optional, Any, IO  # noqa
from .cell import BaseCell, Hash  # noqa
from . import jupyter_messaging as jupy

log = logging.getLogger('knitj')


# #server
# def __init__(self, source: os.PathLike, output: os.PathLike,
#              browser: webbrowser.BaseBrowser = None,
#              kernel: str = None) -> None:


async def convert(source: IO[str], output: IO[str], fmt: str,
                  kernel_name: str = None) -> None:
    parser = Parser(fmt)
    cells = parser.parse(source.read())
    document = Document(cells)
    kernel = Kernel(document.process_message, kernel_name, log.info)
    runner = asyncio.ensure_future(kernel.run())

    template = Template(resource_string('knitj', 'client/templates/index.html'))
    index = template.render(
        cells='__CELLS__',
        styles='\n'.join(chain(
            [HtmlFormatter(style=get_style_by_name('trac')).get_style_defs()],
            map(str, ansi2html.style.get_styles())
        )),
        client=False,
    )

    front, back = index.split('__CELLS__')
    await kernel.wait_for_start()
    for hashid, cell in document.cells.items():
        if isinstance(cell, CodeCell):
            kernel.execute(cell.hashid, cell.code)

    output.write(front)
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


class KnitJ:
    def __init__(self, source: os.PathLike, output: os.PathLike = None,
                 browser: webbrowser.BaseBrowser = None, quiet: bool = False,
                 kernel: str = None) -> None:
        self.source = Path(source)
        self._output_given = bool(output)
        self.output = Path(output) if output else self.source.with_suffix('.html')
        self.quiet = quiet
        self._kernel = Kernel(self._kernel_handler, kernel, self.log)
        self._server = Server(self._get_html, self._nb_msg_handler, browser=browser)
        self._parser = Parser('python' if self.source.suffix == '.py' else 'markdown')
        self._runner: Optional[asyncio.Future] = None
        if self.source.exists():
            cells = self._parser.parse(self.source.read_text())
        else:
            cells = []
        self._document = Document(cells)
        if not self.output or not self.output.exists():
            return
        self._document.load_output_from_html(self.output.read_text())

    async def run(self) -> None:
        self._runner = asyncio.gather(
            self._kernel.run(),
            self._server.run(),
            Source(self._source_handler, self.source).run(),
        )
        await self._runner

    def _kernel_handler(self, msg: jupy.Message, hashid: Hash) -> None:
        cell = self._document.process_message(msg, hashid)
        if not cell:
            return
        self._broadcast(dict(
            kind='cell',
            hashid=cell.hashid,
            html=cell.html,
        ))

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
            cell = self._document.cells[hashid]
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
        self._save_output()

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

    def _save_output(self) -> None:
        if self.output:
            self.output.write_text(self._server.get_index())

    def _get_html(self) -> str:
        return '\n'.join(cell.html for cell in self._document.cells.values())

    async def _write_to_file(self, f, front, back):
        f.write(front)
        try:
            for hashid, cell in self._document.cells.items():
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
        for hashid, cell in self._document.cells.items():
            if isinstance(cell, CodeCell):
                self._kernel.execute(cell.hashid, cell.code)
        if self._output_given:
            with self.output.open('w') as f:
                await self._write_to_file(f, front, back)
        else:
            await self._write_to_file(sys.stdout, front, back)
