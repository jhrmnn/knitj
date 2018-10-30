# Any copyright is dedicated to the Public Domain.
# http://creativecommons.org/publicdomain/zero/1.0/
from enum import Enum
from typing import Dict, List, cast, Any

# flake8: noqa: B903


class Status(Enum):
    OK = 'ok'
    ERROR = 'error'
    ABORTED = 'aborted'


class StreamName(Enum):
    STDOUT = 'stdout'
    STDERR = 'stderr'


class MIME(Enum):
    TEXT_PLAIN = 'text/plain'
    TEXT_HTML = 'text/html'
    IMAGE_PNG = 'image/png'
    IMAGE_SVG_XML = 'image/svg+xml'


class ExecutionState(Enum):
    BUSY = 'busy'
    IDLE = 'idle'
    STARTING = 'starting'


class BaseContent:
    def __repr__(self) -> str:
        dct = vars(self).copy()
        if 'data' in dct:
            dct['data'] = {
                mime: data if len(data) <= 10 else f'{data[:7]}...'
                for mime, data in dct['data'].items()
            }
        if len(dct.get('code', '')) > 20:
            dct['code'] = f'{dct["code"][:17]}...'
        return repr(dct)


class ExecuteRequestContent(BaseContent):
    def __init__(
        self,
        *,
        code: str,
        silent: bool,
        store_history: bool,
        user_expressions: Dict,
        allow_stdin: bool,
        stop_on_error: bool,
    ) -> None:
        self.code = code
        self.silent = silent
        self.store_history = store_history
        self.user_expressions = user_expressions
        self.allow_stdin = allow_stdin
        self.stop_on_error = stop_on_error


class BaseExecuteReplyContent(BaseContent):
    pass


class ExecuteReplyOkContent(BaseExecuteReplyContent):
    def __init__(
        self,
        *,
        status: str,
        execution_count: int,
        payload: List[Dict] = None,
        user_expressions: Dict = None,
    ) -> None:
        self.status = Status(status)
        self.execution_count = execution_count
        self.payload = payload
        self.user_expressions = user_expressions


class ExecuteReplyErrorContent(BaseExecuteReplyContent):
    def __init__(
        self,
        *,
        status: str,
        ename: str,
        evalue: str,
        traceback: List[str],
        **kwargs: Any,
    ) -> None:
        self.status = Status(status)
        self.ename = ename
        self.evalue = evalue
        self.traceback = traceback


class ExecuteReplyAbortedContent(BaseExecuteReplyContent):
    def __init__(self, *, status: str) -> None:
        self.status = Status(status)


def parse_execute_reply(content: Dict) -> BaseExecuteReplyContent:
    status = Status(content['status'])
    if status == Status.OK:
        return ExecuteReplyOkContent(**content)
    if status == Status.ERROR:
        return ExecuteReplyErrorContent(**content)
    if status == Status.ABORTED:
        return ExecuteReplyAbortedContent(**content)
    assert False


class StreamContent(BaseContent):
    def __init__(self, *, name: str, text: str) -> None:
        self.name = StreamName(name)
        self.text = text


class DisplayDataContent(BaseContent):
    def __init__(self, *, data: Dict, metadata: Dict, transient: Dict = None) -> None:
        self.data = {MIME(k): cast(str, v) for k, v in data.items()}
        self.metadata = metadata
        self.transient = transient


class ExecuteInputContent(BaseContent):
    def __init__(self, *, code: str, execution_count: int) -> None:
        self.code = code
        self.execution_count = execution_count


class ExecuteResultContent(BaseContent):
    def __init__(self, *, execution_count: int, data: Dict, metadata: Dict) -> None:
        self.execution_count = execution_count
        self.data = {MIME(k): cast(str, v) for k, v in data.items()}
        self.metadata = metadata


class KernelStatusContent(BaseContent):
    def __init__(self, *, execution_state: str) -> None:
        self.execution_state = ExecutionState(execution_state)


class ShutdownReplyContent(BaseContent):
    def __init__(self, *, restart: bool, status: str) -> None:
        self.restart = restart
        self.status = status
