# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import hashlib
import html
from abc import ABCMeta, abstractmethod

from misaka import Markdown, HtmlRenderer
import pygments
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

from .jupyter_messaging.content import MIME

from typing import Dict, NewType, Optional  # noqa

Hash = NewType('Hash', str)

_md = Markdown(
    HtmlRenderer(),
    extensions='fenced-code math math_explicit tables quote'.split()
)


def _get_hash(s: str) -> Hash:
    return Hash(hashlib.sha1(s.encode()).hexdigest())


class BaseCell(metaclass=ABCMeta):
    def __init__(self) -> None:
        self._html: Optional[str] = None
        self.hashid: Hash

    @property
    def html(self) -> str:
        if self._html is None:
            self._html = self._to_html()
        return self._html

    @abstractmethod
    def _to_html(self) -> str:
        ...


class TextCell(BaseCell):
    def __init__(self, content: str) -> None:
        super().__init__()
        self.content = content
        self.hashid = Hash(_get_hash(content) + '-text')

    def __repr__(self) -> str:
        return f'<TextCell hashid={self.hashid!r} content={self.content!r}>'

    def _to_html(self) -> str:
        return f'<div class="{self.hashid} text-cell">{_md(self.content)}</div>'


class CodeCell(BaseCell):
    def __init__(self, code: str) -> None:
        super().__init__()
        self.code = code
        self._output: Optional[Dict[MIME, str]] = None
        self._stream = ''
        self.hashid = Hash(_get_hash(code) + '-code')

    def __repr__(self) -> str:
        return (
            f'<CodeCell hashid={self.hashid!r} code={self.code!r} '
            f'output={self._output!r}>'
        )

    def append_stream(self, s: str) -> None:
        self._stream += s
        self._html = None

    def set_output(self, output: Optional[Dict[MIME, str]]) -> None:
        self._output = output
        self._html = None

    def _to_html(self) -> str:
        code = pygments.highlight(self.code, PythonLexer(), HtmlFormatter())
        if self._output is None:
            output = ''
        elif MIME.IMAGE_PNG in self._output:
            output = f'<img src="data:image/png;base64,{self._output[MIME.IMAGE_PNG]}">'
        elif MIME.TEXT_HTML in self._output:
            output = self._output[MIME.TEXT_HTML]
        elif MIME.TEXT_PLAIN in self._output:
            output = f'<pre>{html.escape(self._output[MIME.TEXT_PLAIN])}</pre>'
        else:
            assert False
        if self._stream:
            output = f'<pre>{self._stream}</pre>{output}'
        content = f'<div class="code">{code}</div><div class="output">{output}</div>'
        return f'<div class="{self.hashid} code-cell">{content}</div>'
