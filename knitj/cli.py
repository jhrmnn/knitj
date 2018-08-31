# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import sys
import argparse
import asyncio
from pathlib import Path
import logging
from contextlib import contextmanager

import webbrowser

from typing import Optional, Iterator, IO

from .knitj import KnitjServer, convert


def parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    arg = parser.add_argument
    arg('source', type=Path, metavar='FILE', nargs='?', help='input file')
    arg('-o', '--output', type=Path, metavar='FILE', help='output HTML file')
    arg('-b', '--browser', type=webbrowser.get, default=webbrowser.get(),
        help='browser to open')
    arg('-n', '--no-browser', dest='browser', action='store_false',
        help='do not open a browser')
    arg('-s', '--server', action='store_true', help='run in server mode')
    arg('-k', '--kernel', help='Jupyter kernel to use')
    arg('-f', '--format', help='Input format')
    return parser.parse_args()


def main() -> None:
    args = parse_cli()
    fmt: Optional[str] = None
    if args.format:
        fmt = args.format
    elif args.source:
        if args.source.suffix == '.py':
            fmt = 'python'
        elif args.source.suffix == '.md':
            fmt = 'markdown'
    if not fmt:
        raise RuntimeError('Cannot determine input format')
    logging.basicConfig(level=logging.INFO)
    loop = asyncio.get_event_loop()
    if args.server:
        assert args.source
        if args.output:
            output = args.output
        else:
            output = args.source.with_suffix('.html')
        app = KnitjServer(
            args.source, output, fmt, args.browser, args.kernel
        )
        try:
            loop.run_until_complete(app.run())
        except KeyboardInterrupt:
            loop.run_until_complete(app.cleanup())
    else:
        with maybe_input(args.source) as source, \
                maybe_output(args.output) as output:
            loop.run_until_complete(convert(source, output, fmt, args.kernel))
    loop.close()


@contextmanager
def maybe_input(path: Optional[Path]) -> Iterator[IO[str]]:
    if path:
        with path.open() as f:
            yield f
    else:
        yield sys.stdin


@contextmanager
def maybe_output(path: Optional[Path]) -> Iterator[IO[str]]:
    if path:
        with path.open('w') as f:
            yield f
    else:
        yield sys.stdout
