// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/.

/* eslint-env browser */

function h(tagName, func) {
  const el = document.createElement(tagName);
  func(el);
  return el;
}

function elemFromHtml(html) {
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
    button.onclick = () => { reevaluate(cell.id); };
    button.textContent = 'Reevaluate';
  }));
}

ws.onmessage = ({ data }) => {
  const msg = JSON.parse(data);
  if (msg.kind === 'cell') {
    console.log(msg.content);
    const cell = elemFromHtml(msg.html);
    appendReevaluate(cell);
    const origCell = document.getElementById(msg.hashid);
    origCell.replaceWith(cell);
  } else if (msg.kind === 'document') {
    const cellsEl = h('div', (div) => { div.id = 'cells'; });
    msg.hashids.forEach((hashid) => {
      let cell = document.getElementById(hashid);
      if (!cell) {
        cell = elemFromHtml(msg.htmls[hashid]);
        if (cell.className === 'output-cell') {
          appendReevaluate(cell);
        }
      }
      cellsEl.appendChild(cell);
    });
    document.getElementById('cells').replaceWith(cellsEl);
  }
};
