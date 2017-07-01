# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import hashlib
import html
from abc import ABCMeta, abstractmethod
import asyncio
import re

from misaka import Markdown, HtmlRenderer
import pygments
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

from .jupyter_messaging.content import MIME

from typing import Dict, NewType, Optional, Set  # noqa

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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseCell):
            return NotImplemented  # type: ignore
        return type(self) is type(other) and self.hashid == other.hashid


class CodeCell(BaseCell):
    def __init__(self, code: str) -> None:
        super().__init__()
        m = re.match(r'#\s*::', code)
        if m:
            modeline, code = code[m.end():].split('\n', 1)
            modeline = re.sub(r'[^a-z]', '', modeline)
            self.flags = set(modeline.split())
        else:
            self.flags = set()
        self.code = code
        self.hashid = Hash(_get_hash(code) + '-code')
        self._output: Optional[Dict[MIME, str]] = None
        self._stream = ''
        self._done = asyncio.get_event_loop().create_future()
        self._flags: Set[str] = set()

    def __repr__(self) -> str:
        return (
            f'<CodeCell hashid={self.hashid!r} code={self.code!r} '
            f'output={self._output!r}>'
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CodeCell):
            return NotImplemented  # type: ignore
        return super().__eq__(other) and self.flags == other.flags

    def update_flags(self, other: 'CodeCell') -> bool:
        update = self.flags != other.flags
        if update:
            self.flags = other.flags.copy()
            self._html = None
        return update

    def append_stream(self, s: str) -> None:
        self._stream += s
        self._html = None

    def set_output(self, output: Optional[Dict[MIME, str]]) -> None:
        self._output = output
        self._html = None

    def reset(self) -> None:
        self._output = None
        self._stream = ''
        self._html = None
        self._flags.discard('done')
        self._done = asyncio.get_event_loop().create_future()

    def set_done(self) -> None:
        self._flags.discard('evaluating')
        self._flags.add('done')
        self._html = None
        self._done.set_result(None)

    def done(self) -> bool:
        return self._done.done()

    async def wait_for(self) -> None:
        await self._done

    def _to_html(self) -> str:
        code = pygments.highlight(self.code, PythonLexer(), HtmlFormatter())
        if self._output is None:
            output = ''
        elif MIME.IMAGE_PNG in self._output:
            output = f'<img src="data:image/png;base64,{self._output[MIME.IMAGE_PNG]}">'
        elif MIME.TEXT_HTML in self._output:
            output = self._output[MIME.TEXT_HTML]
        elif MIME.TEXT_PLAIN in self._output:
            output = '<pre>' + html.escape(self._output[MIME.TEXT_PLAIN]) + '</pre>'
        else:
            assert False
        if self._stream:
            output = '<pre>' + html.escape(self._stream) + '</pre>' + output
        content = '<div class="code">' + code + '</div>' + \
            '<div class="output">' + output + '</div>'
        classes = [self.hashid, 'code-cell']
        classes.extend(self.flags)
        classes.extend(self._flags)
        return f'<div class="{" ".join(classes)}">{content}</div>'
