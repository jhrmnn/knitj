# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import re

from .Cell import BaseCell, TextCell, CodeCell

from typing import List


class ParsingError(Exception):
    pass


class Parser:
    def parse(self, text: str) -> List[BaseCell]:
        text = text.rstrip()
        cells: List[BaseCell] = []
        buffer = ''
        while text:
            m = re.search(r'((?<=\n)|^)```python|<!--|$', text)
            if m.group(0) == '```python' or not m.group(0):
                buffer += text[:m.start()]
                buffer = buffer.strip()
                if buffer:
                    cells.append(TextCell(buffer))
                    buffer = ''
                text = text[m.end():]
            if m.group(0) == '```python':
                m = re.search(r'(?<=\n)```(?=\s*\n|$)', text)
                if not m:
                    raise ParsingError('Unclosed Python cell')
                code = text[:m.start()].strip()
                cells.append(CodeCell(code))
                text = text[m.end():]
            elif m.group(0) == '<!--':
                m = re.search(r'-->', text)
                if not m:
                    raise ParsingError('Unclosed HTML comment')
                buffer += text[:m.end()]
                text = text[m.end():]
        return cells
