# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging
from collections import OrderedDict

from typing import List, Optional

import ansi2html
from bs4 import BeautifulSoup

from .cell import BaseCell, Hash, CodeCell
from . import jupyter_messaging as jupy
from .jupyter_messaging.content import MIME

ansi_convert = ansi2html.Ansi2HTMLConverter().convert
log = logging.getLogger('knitj.document')


class Document:
    def __init__(self, cells: List[BaseCell]) -> None:
        self.cells = OrderedDict((cell.hashid, cell) for cell in cells)

    def process_message(self, msg: jupy.Message, hashid: Hash
                        ) -> Optional[BaseCell]:
        try:
            cell = self.cells[hashid]
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
                cell.set_done()
        elif isinstance(msg, jupy.ERROR):
            log.info('Got an error')
            html = ansi_convert(
                '\n'.join(msg.content.traceback), full=False
            )
            cell.set_error(html)
        elif isinstance(msg, (jupy.STATUS, jupy.EXECUTE_INPUT)):
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
            if cell_tag.attrs['class'][0] in self.cells:
                cell = self.cells[Hash(cell_tag.attrs['class'][0])]
                assert isinstance(cell, CodeCell)
                cell.set_output({
                    MIME.TEXT_HTML: str(cell_tag.find(class_='output'))
                })
                if 'done' in cell_tag.attrs['class']:
                    cell.set_done()
                if 'hide' in cell_tag.attrs['class']:
                    cell.flags.add('hide')
