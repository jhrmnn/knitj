from .styles import Style

class Formatter:
    def get_style_defs(self) -> str: ...

class HtmlFormatter(Formatter):
    def __init__(self, style: Style = None) -> None: ...
