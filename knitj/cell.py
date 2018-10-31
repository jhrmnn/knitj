# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import re
import hashlib
import html
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Optional, Set

from misaka import Markdown, HtmlRenderer
import pygments
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonLexer

from .jupyter_messaging.content import MIME


_md = Markdown(
    HtmlRenderer(), extensions='fenced-code math math-explicit tables quote'.split()
)


class Hash:
    def __init__(self, value: str) -> None:
        self._value = value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Hash):
            return NotImplemented
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __str__(self) -> str:
        return self._value[:6]

    def __repr__(self) -> str:
        return f'Hash({repr(self._value)})'

    @property
    def value(self) -> str:
        return self._value

    @classmethod
    def from_string(cls, s: str) -> 'Hash':
        return cls(hashlib.sha1(s.encode()).hexdigest())


class BaseCell(ABC):
    def __init__(self, content: str) -> None:
        self._html: Optional[str] = None
        self._hashid = Hash.from_string(content)

    @property
    def hashid(self) -> Hash:
        return self._hashid

    @property
    def html(self) -> str:
        if self._html is None:
            self._html = self.to_html()
        return self._html

    @abstractmethod
    def to_html(self) -> str:
        ...


class TextCell(BaseCell):
    def __init__(self, content: str) -> None:
        BaseCell.__init__(self, 'text' + content)
        self._content = content

    def __repr__(self) -> str:
        return f'<TextCell hashid={self.hashid!r} content={self._content!r}>'

    def to_html(self) -> str:
        return f'<div class="{self.hashid.value} text-cell">{_md(self._content)}</div>'

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseCell):
            return NotImplemented
        return type(self) is type(other) and self.hashid == other.hashid


class CodeCell(BaseCell):
    def __init__(self, code: str) -> None:
        BaseCell.__init__(self, 'code' + code)
        m = re.match(r'#\s*::', code)
        if m:
            try:
                modeline, code = code[m.end() :].split('\n', 1)
            except ValueError:
                modeline, code = code, ''
            modeline = re.sub(r'[^a-z]', '', modeline)
            self.flags = set(modeline.split())
        else:
            self.flags = set()
        self._code = code
        self._output: Optional[Dict[MIME, str]] = None
        self._error: Optional[str] = None
        self._stream = ''
        self._done = asyncio.get_event_loop().create_future()
        self._flags: Set[str] = set()

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} hashid={self.hashid!r} '
            f'code={self._code!r} output={self._output!r}>'
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CodeCell):
            return NotImplemented
        return super().__eq__(other) and self.flags == other.flags

    @property
    def code(self) -> str:
        return self._code

    def update_flags(self, other: 'CodeCell') -> bool:
        update = self.flags != other.flags
        if update:
            self.flags = other.flags.copy()
            self._html = None
        return update

    def append_stream(self, s: str) -> None:
        if s[0] == '\r':
            self._stream = '\n'.join(self._stream.split('\n')[:-1])
            s = s[1:]
        self._stream += s
        self._html = None

    def set_output(self, output: Dict[MIME, str]) -> None:
        self._output = output
        self._html = None

    def set_error(self, error: str) -> None:
        self._error = error
        self._html = None

    def reset(self) -> None:
        self._output = None
        self._error = None
        self._stream = ''
        self._html = None
        self._flags.discard('done')
        self._done = asyncio.get_event_loop().create_future()

    def set_done(self) -> None:
        self._flags.discard('evaluating')
        self._flags.add('done')
        self._html = None
        if not self.done():
            self._done.set_result(None)

    def done(self) -> bool:
        return self._done.done()

    async def wait_for(self) -> None:
        await self._done

    def to_html(self) -> str:
        code = pygments.highlight(self._code, PythonLexer(), HtmlFormatter())
        if self._output is None:
            output = ''
        elif MIME.IMAGE_SVG_XML in self._output:
            m = re.search(r'<svg', self._output[MIME.IMAGE_SVG_XML])
            assert m
            output = self._output[MIME.IMAGE_SVG_XML][m.start() :]
        elif MIME.IMAGE_PNG in self._output:
            output = (
                '<img alt="" src="data:image/png;base64,'
                + self._output[MIME.IMAGE_PNG]
                + '"/>'
            )
        elif MIME.TEXT_HTML in self._output:
            output = self._output[MIME.TEXT_HTML]
        elif MIME.TEXT_PLAIN in self._output:
            output = '<pre>' + html.escape(self._output[MIME.TEXT_PLAIN]) + '</pre>'
        else:
            assert False
        if self._error:
            output = '<pre>' + self._error + '</pre>' + output
        if self._stream:
            output = '<pre>' + html.escape(self._stream) + '</pre>' + output
        content = f'<div class="code">{code}</div><div class="output">{output}</div>'
        classes = [self.hashid.value, 'code-cell']
        classes.extend(self.flags)
        classes.extend(self._flags)
        return f'<div class="{" ".join(classes)}">{content}</div>'


class JinjaCell(CodeCell):
    def __init__(self, template: str) -> None:
        code = f'# ::hide\nprint(jinja2.Template({template!r}).render(locals()))'
        CodeCell.__init__(self, code)
        self._template = template

    def append_stream(self, s: str) -> None:
        super().set_output({MIME.TEXT_HTML: _md(s)})
