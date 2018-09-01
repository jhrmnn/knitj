# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging
from collections import OrderedDict

import ansi2html
from bs4 import BeautifulSoup

from .parser import Parser
from . import jupyter_messaging as jupy
from .jupyter_messaging.content import MIME

from typing import List, Optional, Tuple, Iterator, Dict
from .cell import BaseCell, Hash, CodeCell

ansi_convert = ansi2html.Ansi2HTMLConverter().convert
log = logging.getLogger('knitj.document')


class Document:
    def __init__(self, parser: Parser) -> None:
        self._parser = parser
        self._cells: Dict[Hash, BaseCell] = OrderedDict()

    def items(self) -> Iterator[Tuple[Hash, BaseCell]]:
        yield from self._cells.items()

    def __iter__(self) -> Iterator[BaseCell]:
        yield from self._cells.values()

    def __getitem__(self, hashid: Hash) -> BaseCell:
        return self._cells[hashid]

    def __len__(self) -> int:
        return len(self._cells)

    def hashes(self) -> List[Hash]:
        return list(self._cells)

    def process_message(self, msg: jupy.Message, hashid: Hash
                        ) -> Optional[BaseCell]:
        try:
            cell = self._cells[hashid]
        except KeyError:
            log.warning('Cell does not exist anymore')
            return None
        assert isinstance(cell, CodeCell)
        if isinstance(msg, jupy.EXECUTE_RESULT):
            log.info('Got an execution result')
            cell.set_output(msg.content.data)
        elif isinstance(msg, jupy.STREAM):
            cell.append_stream(msg.content.text)
        elif isinstance(msg, jupy.DISPLAY_DATA):
            log.info('Got a picture')
            cell.set_output(msg.content.data)
        elif isinstance(msg, jupy.EXECUTE_REPLY):
            if isinstance(msg.content, jupy.content.ERROR):
                log.info('Got an error execution reply')
                html = ansi_convert(
                    '\n'.join(msg.content.traceback), full=False
                )
                cell.set_error(html)
            elif isinstance(msg.content, jupy.content.OK):
                log.info('Got an execution reply')
        elif isinstance(msg, jupy.ERROR):
            log.info('Got an error')
            html = ansi_convert(
                '\n'.join(msg.content.traceback), full=False
            )
            cell.set_error(html)
        elif isinstance(msg, jupy.STATUS):
            if msg.content.execution_state == jupy.content.State.IDLE:
                log.info('Cell done')
                cell.set_done()
        elif isinstance(msg, jupy.EXECUTE_INPUT):
            pass
        else:
            raise ValueError(f'Unknown message type: {type(msg)}')
        return cell

    def load_output_from_html(self, html: str) -> None:
        soup = BeautifulSoup(html, 'html.parser')
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

    def update_from_source(self, source: str
                           ) -> Tuple[List[BaseCell], List[BaseCell]]:
        cells = self._parser.parse(source)
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
                new_cells.append(cell)
        self._cells = OrderedDict(
            (cell.hashid, self._cells.get(cell.hashid, cell)) for cell in cells
        )
        return new_cells, updated_cells
