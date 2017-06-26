from .lexers import Lexer
from .formatters import Formatter


def highlight(code: str, lexer: Lexer, formatter: Formatter) -> str:
    ...
