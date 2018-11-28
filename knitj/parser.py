# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import re
import yaml

from .cell import BaseCell, TextCell, CodeCell, JinjaCell

from typing import List, Tuple, Any, Optional, Dict


class ParsingError(Exception):
    pass


class Parser:
    def __init__(self, fmt: str) -> None:
        if fmt == 'markdown':
            self._parser = parse_markdown
        elif fmt == 'python':
            self._parser = parse_python
        else:
            raise ValueError(f'Unknown format: {fmt}')

    def parse(self, text: str) -> Tuple[Optional[Dict[str, Any]], List[BaseCell]]:
        frontmatter, cells = self._parser(text)
        if frontmatter is not None:
            return yaml.load(frontmatter), cells
        return None, cells


def parse_markdown(text: str) -> Tuple[Optional[str], List[BaseCell]]:
    m = re.match(r'^---\n((.*\n)*)---\n', text)
    if m:
        text = text[m.end() :]
        frontmatter: Optional[str] = m.group(1)
    else:
        frontmatter = None
    text = text.rstrip()
    cells: List[BaseCell] = []
    buffer = ''
    while text:
        m = re.search(r'((?<=\n)|^)```python|<!--|$', text)
        assert m
        if m.group(0) == '```python' or not m.group(0):
            buffer += text[: m.start()]
            buffer = buffer.strip()
            if buffer:
                cells.append(TextCell(buffer))
                buffer = ''
            text = text[m.end() :]
        if m.group(0) == '```python':
            m = re.search(r'(?<=\n)```(?=\s*\n|$)', text)
            if not m:
                raise ParsingError('Unclosed Python cell')
            code = text[: m.start()].strip()
            cells.append(CodeCell(code))
            text = text[m.end() :]
        elif m.group(0) == '<!--':
            m = re.search(r'-->', text)
            if not m:
                raise ParsingError('Unclosed HTML comment')
            buffer += text[: m.end()]
            text = text[m.end() :]
    return frontmatter, cells


def parse_python(text: str) -> Tuple[Optional[str], List[BaseCell]]:
    m = re.match(r'^# ---\n((# .*\n)*)# ---\n', text)
    if m:
        text = text[m.end() :]
        frontmatter: Optional[str] = '\n'.join(
            l[2:] for l in m.group(1).split('\n')[:-1]
        )
    else:
        frontmatter = None
    text = text.rstrip()
    cells: List[BaseCell] = []
    buffer = ''
    while text:
        m = re.search(r'((?<=\n)|^)# ?::>|$', text)
        assert m
        buffer += text[: m.start()]
        buffer = buffer.strip()
        if buffer:
            buffer = re.sub(r'((?<=\n)|^)#\s*::%', '%', buffer)
            cells.append(CodeCell(buffer))
            buffer = ''
        text = text[m.end() :]
        if m.group(0):
            m = re.search(r'(?<=\n)[^#]|$', text)
            if not m:
                raise ParsingError('Unclosed Markdown cell')
            chunk, text = text[: m.start()], text[m.start() :]
            assert chunk[0] in {'\n', 'j'}
            is_jinja = chunk[0] == 'j'
            if is_jinja:
                chunk = chunk[1:]
            md = re.sub(r'((?<=\n)|^)# ?', '', chunk.strip())
            cells.append(JinjaCell(md) if is_jinja else TextCell(md))
    return frontmatter, cells
