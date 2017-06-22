import asyncio

from typing import Callable, Awaitable, Generator, Any

class WebSocketServerProtocol:
    async def send(self, data: str) -> None: ...
    async def recv(self) -> str: ...

class ConnectionClosed(Exception): ...

@asyncio.coroutine
def serve(ws_handler: Callable[[WebSocketServerProtocol, str], Awaitable[None]],
          host: str,
          port: int) -> Generator[Any, None, Any]: ...
