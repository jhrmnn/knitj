# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from enum import Enum
import hashlib
import html

from misaka import Markdown, HtmlRenderer
import pygments
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

from .jupyter_messaging.content import MIME

from typing import Dict, NewType

Hash = NewType('Hash', str)
HTML = NewType('HTML', str)

_md = Markdown(
    HtmlRenderer(),
    extensions='fenced-code math math_explicit tables quote'.split()
)


def get_hash(s: str) -> Hash:
    return Hash(hashlib.sha1(s.encode()).hexdigest())


class Cell:
    class Kind(Enum):
        TEXT = 0
        INPUT = 1
        OUTPUT = 2

    _html_params = {
        Kind.INPUT: ('div', 'input-cell'),
        Kind.OUTPUT: ('pre', 'output-cell'),
        Kind.TEXT: ('div', 'text-cell'),
    }

    def __init__(self, kind: Kind, content: Dict[MIME, str], hashid: Hash) -> None:
        self.kind = kind
        self.content = content
        self.hashid = hashid

    def __repr__(self) -> str:
        return f'<Cell kind={self.kind!r} hashid={self.hashid!r} content={self.content!r}>'

    def to_html(self) -> HTML:
        if MIME.IMAGE_PNG in self.content:
            content = f'<img src="data:image/png;base64,{self.content[MIME.IMAGE_PNG]}">'
        elif MIME.TEXT_HTML in self.content:
            content = self.content[MIME.TEXT_HTML]
        elif MIME.TEXT_MARKDOWN in self.content:
            content = _md(self.content[MIME.TEXT_MARKDOWN])
        elif MIME.TEXT_PLAIN in self.content:
            content = html.escape(self.content[MIME.TEXT_PLAIN])
        elif MIME.TEXT_PYTHON in self.content:
            content = pygments.highlight(
                self.content[MIME.TEXT_PYTHON], PythonLexer(), HtmlFormatter()
            )
        else:
            raise ValueError(f'Unknown MIME types: {list(self.content)}')
        elem, klass = Cell._html_params[self.kind]
        return HTML(
            f'<{elem} id="{self.hashid}" class="{klass}">{content}</{elem}>'
        )
