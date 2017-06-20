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

const ws = new WebSocket('ws://localhost:6060');

window.setInterval(() => { ws.send(''); }, 50000);

ws.onmessage = (message) => {
  $('#cells').appendChild(h('pre', (pre) => {
    pre.textContent = message.data;
  }));
};
