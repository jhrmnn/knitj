// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at http://mozilla.org/MPL/2.0/.

/* eslint-env browser */
/* global renderMath */

function h(tagName, func) {
  const el = document.createElement(tagName);
  func(el);
  return el;
}

function elemFromHtml(html) {
  const div = document.createElement('div');
  div.innerHTML = html;
  const el = div.childNodes[0];
  Array.from(el.getElementsByTagName('script')).forEach((scr) => {
    const parentEl = scr.parentElement;
    const scrNew = document.createElement('script');
    scrNew.textContent = scr.textContent;
    parentEl.insertBefore(scrNew, scr);
    parentEl.removeChild(scr);
  });
  return el;
}

const ws = new WebSocket(`ws://${document.location.host}/ws`);
let askedForRestart = false;

function send(msg) {
  ws.send(JSON.stringify(msg));
}

window.setInterval(() => { send({ kind: 'ping' }); }, 50000);

function reevaluate(hashid) {
  Array.from(document.getElementsByClassName(hashid)).forEach((cell) => {
    cell.classList.add('evaluating');
    cell.getElementsByClassName('output')[0].innerHTML = '';
  });
  send({ kind: 'reevaluate', hashids: [hashid] });
}

function reevaluateFromHere(hashid) {
  const arr = Array.from(document.getElementById('cells').children);
  const idx = arr.findIndex(cell => cell.classList[0] === hashid);
  const hashids = [];
  arr.slice(idx).forEach((cell) => {
    if (cell.classList.contains('code-cell')) {
      cell.classList.add('evaluating');
      cell.getElementsByClassName('output')[0].innerHTML = '';
      hashids.push(cell.classList[0]);
    }
  });
  send({ kind: 'reevaluate', hashids });
}

function appendReevaluate(cell) {
  cell.appendChild(h('button', (button) => {
    button.onclick = () => { reevaluate(cell.classList[0]); };
    button.textContent = 'Evaluate';
  }));
  cell.appendChild(h('button', (button) => {
    button.onclick = () => { reevaluateFromHere(cell.classList[0]); };
    button.textContent = 'Evaluate all from here';
  }));
  cell.appendChild(h('button', (button) => {
    button.onclick = () => { send({ kind: 'interrupt_kernel' }); };
    button.textContent = 'Interrupt kernel';
  }));
}

function ensureVisible(elem) {
  const rect = elem.getBoundingClientRect();
  const height = window.innerHeight || document.documentElement.clientHeight;
  if (rect.top < 0 || rect.top > height-20) {
    elem.scrollIntoView();
  }
}

ws.onmessage = ({ data }) => {
  const msg = JSON.parse(data);
  if (msg.kind === 'cell') {
    const cell = elemFromHtml(msg.html);
    const arr = Array.from(document.getElementsByClassName(msg.hashid));
    if (arr.length === 1) {
      appendReevaluate(cell);
      arr[0].replaceWith(cell);
      ensureVisible(cell);
    } else {
      let cloned;
      arr.forEach((origCell) => {
        cloned = cell.cloneNode(true);
        appendReevaluate(cloned);
        origCell.replaceWith(cloned);
      });
      ensureVisible(cloned);
    }
  } else if (msg.kind === 'document') {
    const cellsEl = h('div', (div) => { div.id = 'cells'; });
    msg.hashids.forEach((hashid) => {
      const html = msg.htmls[hashid];
      let cell;
      if (html) {
        cell = elemFromHtml(html);
        if (cell.classList.contains('code-cell')) {
          appendReevaluate(cell);
        } else if (cell.classList.contains('text-cell')) {
          renderMath(cell);
        }
      } else {
        cell = document.getElementsByClassName(hashid)[0];
        if (!cell) {
          cell = cellsEl.getElementsByClassName(hashid)[0].cloneNode(true);
        }
      }
      cellsEl.appendChild(cell);
    });
    document.getElementById('cells').replaceWith(cellsEl);
  } else if (msg.kind === 'kernel_starting') {
    if (askedForRestart) {
      askedForRestart = false;
      window.alert('Kernel restarted');
    }
  }
};

Array.from(document.getElementsByClassName('code-cell')).forEach((cell) => {
  appendReevaluate(cell);
});
document.body.insertBefore(h('button', (button) => {
  button.onclick = () => {
    askedForRestart = true;
    send({ kind: 'restart_kernel' });
  };
  button.textContent = 'Restart kernel';
}), document.body.firstChild);
