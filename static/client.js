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

function send(msg) {
  ws.send(JSON.stringify(msg));
}

window.setInterval(() => { send({ kind: 'ping' }); }, 50000);

function reevaluate(hashid) {
  send({ kind: 'reevaluate', hashid });
}

const cells = new Map()

ws.onmessage = ({ data }) => {
  const msg = JSON.parse(data);
  if (msg.kind == 'cell') {
    console.log(msg.content);
    const cell = elem_from_html(msg.content)
    cell.appendChild(h('button', (button) => {
      button.onclick = () => { reevaluate(msg.hashid); };
      button.textContent = 'Reevaluate';
    }));
    const orig_cell = document.getElementById(msg.hashid);
    orig_cell.replaceWith(cell);
    cells[msg.hashid] = cell;
  } else if (msg.kind == 'document') {
    const cells_el = h('div', (div) => { div.id = 'cells'; });
    msg.cells.forEach((hashid) => {
      if (!(hashid in cells)) {
        cells[hashid] = elem_from_html(msg.contents[hashid]);
      }
      cells_el.appendChild(cells[hashid]);
    });
    document.getElementById('cells').replaceWith(cells_el);
  }
};
