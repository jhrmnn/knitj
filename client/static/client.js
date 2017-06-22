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

function appendReevaluate(cell) {
  cell.appendChild(h('button', (button) => {
    button.onclick = () => { reevaluate(msg.hashid); };
    button.textContent = 'Reevaluate';
  }));
}

let last_render = new Map()

ws.onmessage = ({ data }) => {
  const msg = JSON.parse(data);
  if (msg.kind == 'cell') {
    console.log(msg.content);
    const cell = elem_from_html(msg.html)
    appendReevaluate(cell);
    const orig_cell = document.getElementById(msg.hashid);
    orig_cell.replaceWith(cell);
    last_render[msg.hashid] = cell;
  } else if (msg.kind == 'document') {
    const cells_el = h('div', (div) => { div.id = 'cells'; });
    const new_render = new Map();
    msg.hashids.forEach((hashid) => {
      let cell;
      if (hashid in last_render) {
        cell = last_render[hashid];
      } else {
        cell = elem_from_html(msg.htmls[hashid]);
        if (cell.className == 'output-cell') {
          appendReevaluate(cell);
        }
      }
      cells_el.appendChild(cell);
      new_render[hashid] = cell;
    });
    document.getElementById('cells').replaceWith(cells_el);
    last_render = new_render;
  }
};
