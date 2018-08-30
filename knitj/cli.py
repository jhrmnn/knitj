# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from argparse import ArgumentParser
import asyncio
from pathlib import Path

import webbrowser

from .knitj import KnitJ


def parse_cli() -> dict:
    parser = ArgumentParser()
    arg = parser.add_argument
    arg('source', type=Path, metavar='FILE', nargs='?', help='input file')
    arg('-o', '--output', type=Path, metavar='FILE', help='output HTML file')
    arg('-b', '--browser', type=webbrowser.get, default=webbrowser.get(),
        help='browser to open')
    arg('-n', '--no-browser', dest='browser', action='store_false',
        help='do not open a browser')
    arg('-s', '--server', action='store_true', help='run in server mode')
    arg('-k', '--kernel', help='Jupyter kernel to use')
    return vars(parser.parse_args())


def main() -> None:
    kwargs = parse_cli()
    server_mode = kwargs.pop('server')
    if not server_mode:
        kwargs['quiet'] = True
    app = KnitJ(**kwargs)
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(app.run() if server_mode else app.static())
    except KeyboardInterrupt:
        loop.run_until_complete(app.cleanup())
