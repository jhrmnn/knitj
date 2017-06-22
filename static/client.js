// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/.
/* eslint-env browser */

function $(query) { return document.querySelector(query); }

function h(tagName, func) {
  const el = document.createElement(tagName);
  func(el);
  return el;
}

function elem_from_html(html) {
  const el = document.createElement('div');
  el.innerHTML = html;
  return el.childNodes[0];
}

const ws = new WebSocket('ws://localhost:6060');

window.setInterval(() => { ws.send(''); }, 50000);

const cells = new Map()

ws.onmessage = ({ data }) => {
  const msg = JSON.parse(data);
  if (msg.kind == 'cell') {
    const cell = elem_from_html(msg.content)
    const orig_cell = document.getElementById(msg.hashid);
    orig_cell.replaceWith(cell);
  } else if (msg.kind == 'document') {
    const cells_el = h('div', (div) => { div.id = 'cells'; });
    msg.cells.forEach((hashid) => {
      cells_el.appendChild(elem_from_html(msg.contents[hashid]));
    });
    document.getElementById('cells').replaceWith(cells_el);
  }
};
