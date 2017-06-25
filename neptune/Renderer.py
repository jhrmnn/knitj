# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from asyncio import Queue
from typing import NamedTuple
import json

from typing import Set, Union, List, Dict, Any

from .Cell import Cell, Hash, HTML
from .Notebook import Notebook, Data

Document = List[Cell]
RenderTask = Union[Cell, Document]
Msg = Dict[str, Any]


class Render(NamedTuple):
    hashids: List[Hash]
    htmls: Dict[Hash, HTML]


class Renderer:
    def __init__(self, notebooks: Set[Notebook]) -> None:
        self.notebooks = notebooks
        self._task_queue: 'Queue[RenderTask]' = Queue()
        self._last_render = Render([], {})

    def add_task(self, task: RenderTask) -> None:
        self._task_queue.put_nowait(task)

    def _render_cell(self, cell: Cell) -> Msg:
        html = cell.to_html()
        self._last_render.htmls[cell.hashid] = html
        return dict(
            kind='cell',
            hashid=cell.hashid,
            html=html,
        )

    @property
    def _render_msg(self) -> Msg:
        return dict(
            kind='document',
            hashids=self._last_render.hashids,
            htmls=self._last_render.htmls,
        )

    def _render_document(self, document: Document) -> Msg:
        self._last_render = Render(
            [cell.hashid for cell in document],
            {cell.hashid: (
                self._last_render.htmls.get(cell.hashid) or cell.to_html()
            ) for cell in document}
        )
        return self._render_msg

    def get_last_html(self) -> HTML:
        return HTML('\n'.join(
            self._last_render.htmls[hashid]
            for hashid in self._last_render.hashids
        ))

    async def run(self) -> None:
        while True:
            task = await self._task_queue.get()
            if isinstance(task, Cell):
                msg = self._render_cell(task)
            elif isinstance(task, list):
                msg = self._render_document(task)
            data = Data(json.dumps(msg))
            for nb in self.notebooks:
                nb.queue_msg(data)
