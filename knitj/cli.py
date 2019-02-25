# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import sys
import argparse
import asyncio
from pathlib import Path
import logging
import concurrent.futures
from contextlib import contextmanager

import webbrowser

from typing import Optional, Iterator, IO

from .server import KnitjServer
from .convert import convert

logging.basicConfig(
    style='{',
    format='[{asctime}.{msecs:03.0f}] {levelname}:{name}: {message}',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('knitj')
log.setLevel(logging.INFO)


def parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    arg = parser.add_argument
    arg('source', type=Path, metavar='FILE', nargs='?', help='input file')
    arg('-s', '--server', action='store_true', help='run in server mode')
    arg('-f', '--format', help='input format')
    arg('-o', '--output', type=Path, metavar='FILE', help='output HTML file')
    arg('-k', '--kernel', help='Jupyter kernel to use')
    arg('-b', '--browser', help='browser to open')
    arg(
        '-n',
        '--no-browser',
        dest='browser',
        action='store_false',
        help='do not open a browser',
    )
    args = parser.parse_args()
    if args.server and args.source is None:
        parser.error('argument -s/--server: requires input file')
    return args


def main() -> None:
    args = parse_cli()
    log.info('Entered Knitj')
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
    if args.browser is not False:
        browser: Optional[webbrowser.BaseBrowser] = webbrowser.get(args.browser)
    else:
        browser = None
    loop = asyncio.get_event_loop()
    # hack to catch exceptions from kernel channels that run in threads
    executor = concurrent.futures.ThreadPoolExecutor()
    loop.set_default_executor(executor)
    if args.server:
        assert args.source
        if args.output:
            output = args.output
        else:
            output = args.source.with_suffix('.html')
        app = KnitjServer(args.source, output, fmt, browser, args.kernel)
        loop.run_until_complete(app.start())
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        loop.run_until_complete(app.cleanup())
    else:
        with maybe_input(args.source) as source, maybe_output(args.output) as output:
            loop.run_until_complete(convert(source, output, fmt, args.kernel))
    executor.shutdown(wait=True)
    loop.close()
    log.info('Leaving Knitj')


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
