#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from argparse import ArgumentParser
import webbrowser
import asyncio


def parse_cli() -> dict:
    parser = ArgumentParser()
    arg = parser.add_argument
    arg('source', metavar='FILE', help='source file in Markdown format')
    arg('report', metavar='REPORT', nargs='?', help='rendered HTML file')
    arg('-b', '--browser', type=webbrowser.get, default=webbrowser.get(),
        help='browser to open')
    arg('-n', '--no-browser', dest='browser', action='store_false',
        help='do not open a browser')
    arg('-s', '--static', action='store_true', help=(
        'do not watch file for changes, render only once'
    ))
    return vars(parser.parse_args())


def main() -> None:
    kwargs = parse_cli()
    from knitj import KnitJ
    if kwargs.pop('static'):
        task = asyncio.ensure_future(KnitJ(**kwargs, quiet=True).static())  # type: ignore
    else:
        task = asyncio.ensure_future(KnitJ(**kwargs).run())
    try:
        asyncio.get_event_loop().run_until_complete(task)
    except KeyboardInterrupt:
        task.cancel()
        asyncio.get_event_loop().run_forever()


if __name__ == '__main__':
    main()
