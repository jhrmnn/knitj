from . import style


class Ansi2HTMLConverter:
    def convert(self, ansi: str, full: bool = True) -> str: ...
