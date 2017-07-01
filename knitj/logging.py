# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/
from typing import Any


class colstr(str):
    colors = {
        'red': '\x1b[31m',
        'green': '\x1b[32m',
        'yellow': '\x1b[33m',
        'blue': '\x1b[34m',
        'bryellow': '\x1b[93m',
        'brblue': '\x1b[94m',
        'pink': '\x1b[35m',
        'cyan': '\x1b[36m',
        'grey': '\x1b[37m',
        'normal': '\x1b[0m'
    }

    def __new__(cls, s: Any, color: str) -> str:
        return str.__new__(  # type: ignore
            cls,
            colstr.colors[color] + str(s) + colstr.colors['normal']
        )

    def __init__(self, s: Any, color: str) -> None:
        self.len = len(str(s))
        self.orig = str(s)

    def __len__(self) -> int:
        return self.len
