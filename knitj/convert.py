# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from pathlib import Path
import logging
from itertools import chain
from pkg_resources import resource_string

import ansi2html
import jinja2
from pygments.formatters import HtmlFormatter
from pygments.styles import get_style_by_name

from .cell import CodeCell
from .kernel import Kernel
from .document import Document
from .parser import Parser

from typing import IO, Optional

log = logging.getLogger('knitj.knitj')


def render_index(
    title: str, cells: str, client: bool = True, template: Path = None
) -> str:
    if template:
        index = template.read_text()
    else:
        index = resource_string('knitj', 'client/templates/index.html').decode()
    templ = jinja2.Template(index)
    styles = '\n'.join(
        chain(
            [HtmlFormatter(style=get_style_by_name('trac')).get_style_defs()],
            map(str, ansi2html.style.get_styles()),
        )
    )
    return templ.render(title=title, cells=cells, styles=styles, client=client)


async def convert(
    source: IO[str], output: IO[str], fmt: str, kernel_name: str = None
) -> None:
    document = Document(Parser(fmt))
    document.update_from_source(source.read())
    kernel = Kernel(document.process_message, kernel_name)
    kernel.start()
    try:
        template: Optional[Path] = Path(document.frontmatter['template'])
    except KeyError:
        template = None
    front, back = render_index('', '__CELLS__', client=False, template=template).split(
        '__CELLS__'
    )
    output.write(front)
    for _, cell in document.items():
        if isinstance(cell, CodeCell):
            kernel.execute(cell.hashid, cell.code)
    log.info('Code cells submitted to kernel')
    for _, cell in document.items():
        if isinstance(cell, CodeCell):
            await cell.wait_for()
        output.write(cell.html)
    output.write(back)
    await kernel.cleanup()
