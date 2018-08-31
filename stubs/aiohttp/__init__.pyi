from typing import Any


class WSMsgType:
    TEXT: 'WSMsgType'
    ERROR: 'WSMsgType'


class WSMessage:
    type: WSMsgType
    def json(self) -> Any: ...


class WSCloseCode:
    pass
