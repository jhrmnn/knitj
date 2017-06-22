from typing import Awaitable, Callable

class HTTPNotFound(Exception): ...

class BaseRequest:
    path: str

class Response:
    def __init__(self, *, text: str = None, content_type: str = None) -> None: ...

class Server:
    def __init__(self, handler: Callable[[BaseRequest], Awaitable[Response]]) -> None: ...
