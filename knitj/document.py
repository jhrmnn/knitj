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

from typing import List, Optional, Tuple, Iterator, Dict, Any
from .cell import BaseCell, Hash, CodeCell

ansi_convert = ansi2html.Ansi2HTMLConverter().convert
log = logging.getLogger('knitj.document')


class Document:
    def __init__(self, parser: Parser) -> None:
        self._parser = parser
        self._frontmatter: Optional[Dict[str, Any]] = None
        self._cells: Dict[Hash, BaseCell] = OrderedDict()

    def items(self) -> Iterator[Tuple[Hash, BaseCell]]:
        yield from self._cells.items()

    def __iter__(self) -> Iterator[BaseCell]:
        yield from self._cells.values()

    def __getitem__(self, hashid: Hash) -> BaseCell:
        return self._cells[hashid]

    def __len__(self) -> int:
        return len(self._cells)

    @property
    def frontmatter(self) -> Dict[str, Any]:
        return self._frontmatter.copy() if self._frontmatter is not None else {}

    def hashes(self) -> List[Hash]:
        return list(self._cells)

    def process_message(  # noqa: C901
        self, msg: jupy.Message, hashid: Optional[Hash]
    ) -> Optional[BaseCell]:
        if not hashid:
            return None
        try:
            cell = self._cells[hashid]
        except KeyError:
            log.warning(f'{hashid}: Cell does not exist anymore')
            return None
        assert isinstance(cell, CodeCell)
        if isinstance(msg, jupy.EXECUTE_RESULT):
            log.info(f'{hashid}: Got an execution result')
            cell.set_output(msg.content.data)
        elif isinstance(msg, jupy.STREAM):
            cell.append_stream(msg.content.text)
        elif isinstance(msg, jupy.DISPLAY_DATA):
            log.info(f'{hashid}: Got a picture')
            cell.set_output(msg.content.data)
        elif isinstance(msg, jupy.EXECUTE_REPLY):
            if isinstance(msg.content, jupy.content.ERROR):
                log.info(f'{hashid}: Got an error execution reply')
                html = ansi_convert('\n'.join(msg.content.traceback), full=False)
                cell.set_error(html)
            elif isinstance(msg.content, jupy.content.OK):
                log.info(f'{hashid}: Got an execution reply')
        elif isinstance(msg, jupy.ERROR):
            log.info(f'{hashid}: Got an error')
            html = ansi_convert('\n'.join(msg.content.traceback), full=False)
            cell.set_error(html)
        elif isinstance(msg, jupy.STATUS):
            if msg.content.execution_state == jupy.content.State.IDLE:
                log.info(f'{hashid}: Cell done')
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
        n_loaded = 0
        for cell_tag in cells_tag.find_all('div', class_='code-cell'):
            hashid = Hash(cell_tag.attrs['class'][0])
            if hashid in self._cells:
                n_loaded += 1
                cell = self._cells[hashid]
                assert isinstance(cell, CodeCell)
                cell.set_output({MIME.TEXT_HTML: str(cell_tag.find(class_='output'))})
                if 'done' in cell_tag.attrs['class']:
                    cell.set_done()
                if 'hide' in cell_tag.attrs['class']:
                    cell.flags.add('hide')
        log.info(f'{n_loaded} code cells loaded from output')

    def update_from_source(self, source: str) -> Tuple[List[BaseCell], List[BaseCell]]:
        frontmatter, cell_list = self._parser.parse(source)
        if frontmatter is not None:
            self._frontmatter = frontmatter
        cells = OrderedDict((cell.hashid, cell) for cell in cell_list)
        new_cells = []
        cells_with_updated_flags: List[BaseCell] = []
        for hashid, cell in cells.items():
            if hashid in self._cells:
                old_cell = self._cells[cell.hashid]
                if isinstance(old_cell, CodeCell):
                    assert isinstance(cell, CodeCell)
                    if old_cell.update_flags(cell):
                        cells_with_updated_flags.append(old_cell)
            else:
                new_cells.append(cell)
        n_dropped = sum(hashid not in cells for hashid in self._cells)
        log.info(
            f'File change: {len(new_cells)}/{len(self)} new cells, '
            f'{n_dropped} dropped'
        )
        cells = OrderedDict(
            (hashid, self._cells.get(hashid, cell)) for hashid, cell in cells.items()
        )
        self._cells.clear()
        self._cells.update(cells)
        return new_cells, new_cells + cells_with_updated_flags
