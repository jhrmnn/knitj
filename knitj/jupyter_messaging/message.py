# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/
import datetime
from enum import Enum
from pprint import pformat

from typing import NewType, Dict, Any, List

from .content import content as cnt

UUID = NewType('UUID', str)


class MsgType(Enum):
    EXECUTE_REQUEST = 'execute_request'
    EXECUTE_REPLY = 'execute_reply'
    DISPLAY_DATA = 'display_data'
    STREAM = 'stream'
    EXECUTE_INPUT = 'execute_input'
    EXECUTE_RESULT = 'execute_result'
    ERROR = 'error'
    STATUS = 'status'
    SHUTDOWN_REPLY = 'shutdown_reply'
    SHUTDOWN_REQUEST = 'shutdown_request'

    def __str__(self) -> str:
        return colstr(self.name, _msg_colors[self])


_msg_colors = {
    MsgType.EXECUTE_REQUEST: 'bryellow',
    MsgType.EXECUTE_REPLY: 'yellow',
    MsgType.DISPLAY_DATA: 'blue',
    MsgType.STREAM: 'pink',
    MsgType.EXECUTE_INPUT: 'red',
    MsgType.EXECUTE_RESULT: 'cyan',
    MsgType.ERROR: 'red',
    MsgType.STATUS: 'green',
    MsgType.SHUTDOWN_REPLY: 'red',
}


class Header:
    def __init__(
        self,
        *,
        msg_id: UUID,
        username: str,
        session: UUID,
        date: datetime.datetime,
        msg_type: str,
        version: str,
    ) -> None:
        self.msg_id = msg_id
        self.username = username
        self.session = session
        self.date = date
        self.msg_type = MsgType(msg_type)
        self.version = version

    def __repr__(self) -> str:
        return f'(date={self.date} id={self.msg_id} session={self.session})'


class BaseMessage:
    def __init__(
        self,
        *,
        header: Dict,
        parent_header: Dict,
        metadata: Dict,
        buffers: List,
        msg_id: UUID,
        msg_type: str,
    ) -> None:
        self.header = Header(**header)
        self.parent_header = Header(**parent_header) if parent_header else None
        self.metadata = metadata
        self.buffers = buffers
        assert msg_id == self.header.msg_id
        assert MsgType(msg_type) == self.header.msg_type
        assert not buffers

    def __repr__(self) -> str:
        return f'{self.msg_type!s}: {pformat(vars(self))}'

    @property
    def msg_id(self) -> UUID:
        return self.header.msg_id

    @property
    def msg_type(self) -> MsgType:
        return self.header.msg_type


class ExecuteRequestMessage(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = cnt.ExecuteRequestContent(**content)


class ExecuteReplyMessage(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = cnt.parse_execute_reply(content)


class StreamMessage(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = cnt.StreamContent(**content)


class DisplayDataMessage(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = cnt.DisplayDataContent(**content)


class ExecuteInputMessage(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = cnt.ExecuteInputContent(**content)


class ExecuteResultMessage(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = cnt.ExecuteResultContent(**content)


class ErrorMessage(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        content['status'] = 'error'
        self.content = cnt.ExecuteReplyErrorContent(**content)


class KernelStatusMessage(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = cnt.KernelStatusContent(**content)


class ShutdownReplyMessage(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = cnt.ShutdownReplyContent(**content)


_msg_classes = {
    MsgType.EXECUTE_REQUEST: ExecuteRequestMessage,
    MsgType.EXECUTE_REPLY: ExecuteReplyMessage,
    MsgType.DISPLAY_DATA: DisplayDataMessage,
    MsgType.STREAM: StreamMessage,
    MsgType.EXECUTE_INPUT: ExecuteInputMessage,
    MsgType.EXECUTE_RESULT: ExecuteResultMessage,
    MsgType.ERROR: ErrorMessage,
    MsgType.STATUS: KernelStatusMessage,
    MsgType.SHUTDOWN_REPLY: ShutdownReplyMessage,
}


def parse(msg: Dict) -> BaseMessage:
    msg_type = MsgType(msg['msg_type'])
    return _msg_classes[msg_type](**msg)


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
        'normal': '\x1b[0m',
    }

    def __new__(cls, s: Any, color: str) -> str:
        return str.__new__(  # type: ignore
            cls, colstr.colors[color] + str(s) + colstr.colors['normal']
        )

    def __init__(self, s: Any, color: str) -> None:
        self.len = len(str(s))
        self.orig = str(s)

    def __len__(self) -> int:
        return self.len
