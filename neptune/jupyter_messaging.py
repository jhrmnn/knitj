# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

# based on Jupyter messaging version 5.2
import datetime
from enum import Enum
from pprint import pformat

# ~~~ typing imports ~~~
from typing import (  # noqa
    NewType, Dict, Any, List, cast
)
# ~~~ end typing ~~~

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


class Status(Enum):
    OK = 'ok'
    ERROR = 'error'


class StreamName(Enum):
    STDOUT = 'stdout'
    STDERR = 'stderr'


class MIME(Enum):
    TEXT_PLAIN = 'text/plain'
    TEXT_HTML = 'text/html'
    TEXT_MARKDOWN = 'text/markdown'
    TEXT_PYTHON = 'text/python'
    IMAGE_PNG = 'image/png'


class ExeState(Enum):
    BUSY = 'busy'
    IDLE = 'idle'
    STARTING = 'starting'


class Header:
    def __init__(self, *, msg_id: UUID, username: str, session: UUID,
                 date: datetime.datetime, msg_type: str, version: str) -> None:
        self.msg_id = msg_id
        self.username = username
        self.session = session
        self.date = date
        self.msg_type = MsgType(msg_type)
        self.version = version

    def __repr__(self) -> str:
        return f'(date={self.date} id={self.msg_id} session={self.session})'


class BaseContent:
    def __repr__(self) -> str:
        return pformat(vars(self))


class BaseMessage:
    def __init__(self, *, header: Dict, parent_header: Dict, metadata: Dict,
                 buffers: List, msg_id: UUID, msg_type: str) -> None:
        self.header = Header(**header)
        self.parent_header = Header(**parent_header) if parent_header else None
        self.metadata = metadata
        self.buffers = buffers
        assert msg_id == self.header.msg_id
        assert MsgType(msg_type) == self.header.msg_type
        assert not buffers

    def __repr__(self) -> str:
        return pformat(vars(self))

    @property
    def msg_id(self) -> UUID:
        return self.header.msg_id

    @property
    def msg_type(self) -> MsgType:
        return self.header.msg_type


class ExecuteReqCont(BaseContent):
    def __init__(self, *, code: str, silent: bool, store_history: bool,
                 user_expressions: Dict, allow_stdin: bool,
                 stop_on_error: bool) -> None:
        self.code = code
        self.silent = silent
        self.store_history = store_history
        self.user_expressions = user_expressions
        self.allow_stdin = allow_stdin
        self.stop_on_error = stop_on_error


class ExecuteReqMsg(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = ExecuteReqCont(**content)


class ActionReplCont(BaseContent):

    @staticmethod
    def from_dict(content: Dict) -> 'ActionReplCont':
        status = Status(content['status'])
        if status == Status.OK:
            return ActionReplOKCont(**content)
        return ActionReplErrCont(**content)


class ActionReplOKCont(ActionReplCont):
    def __init__(self, *, status: str, execution_count: int,
                 payload: List[Dict] = None, user_expressions: Dict = None) -> None:
        self.status = Status(status)
        self.execution_count = execution_count
        self.payload = payload
        self.user_expressions = user_expressions


class ActionReplErrCont(ActionReplCont):
    def __init__(self, *, status: str, ename: str, evalue: str, traceback: List[str]) -> None:
        self.status = Status(status)
        self.ename = ename
        self.evalue = evalue
        self.traceback = traceback


class ActionReplyMsg(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = ActionReplCont.from_dict(content)


class StreamCont(BaseContent):
    def __init__(self, *, name: str, text: str) -> None:
        self.name = StreamName(name)
        self.text = text


class StreamMsg(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = StreamCont(**content)


class DispDataCont(BaseContent):
    def __init__(self, *, data: Dict, metadata: Dict, transient: Dict = None) -> None:
        self.data = {MIME(k): cast(str, v) for k, v in data.items()}
        self.metadata = metadata
        self.transient = transient


class DispDataMsg(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = DispDataCont(**content)


class ExeInpCont(BaseContent):
    def __init__(self, *, code: str, execution_count: int) -> None:
        self.code = code
        self.execution_count = execution_count


class ExeInpMsg(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = ExeInpCont(**content)


class ExeResultCont(BaseContent):
    def __init__(self, *, execution_count: int, data: Dict, metadata: Dict) -> None:
        self.execution_count = execution_count
        self.data = {MIME(k): cast(str, v) for k, v in data.items()}
        self.metadata = metadata


class ExeResultMsg(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = ExeResultCont(**content)


class ErrorMsg(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        content['status'] = 'error'
        self.content = ActionReplErrCont(**content)


class KernelStatCont(BaseContent):
    def __init__(self, *, execution_state: str) -> None:
        self.execution_state = ExeState(execution_state)


class KernelStatMsg(BaseMessage):
    def __init__(self, *, content: Dict, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.content = KernelStatCont(**content)


class _content:
    OK = ActionReplOKCont
    ERROR = ActionReplErrCont


class JupMsgClass:
    EXECUTE_REQUEST = ExecuteReqMsg
    EXECUTE_REPLY = ActionReplyMsg
    DISPLAY_DATA = DispDataMsg
    STREAM = StreamMsg
    EXECUTE_INPUT = ExeInpMsg
    EXECUTE_RESULT = ExeResultMsg
    ERROR = ErrorMsg
    STATUS = KernelStatMsg
    content = _content

    @staticmethod
    def __call__(msg: Dict) -> BaseMessage:
        msg_type = MsgType(msg['msg_type'])
        return cast(BaseMessage, getattr(JupMsgClass, msg_type.name)(**msg))


JupMsg = JupMsgClass()
