import typing
from datetime import datetime
from exceptions.base import BermoidBaseException

__all__ = ("WebSocketException")


class WebSocketException(BermoidBaseException):
    def __init__(
        self,
        code: int = 1000,
        reason: str | None = None,
        *,
        extra: typing.Optional[dict[str, typing.Any]] = None,
        timestamp: typing.Optional[datetime] = None,
    ) -> None:
        reason = reason or "WebSocket Error"
        self.code = code
        self.reason = reason
        super().__init__(reason, code=str(code), extra=extra, timestamp=timestamp)

    def as_dict(self) -> dict[str, typing.Any]:
        data = super().as_dict()
        data.update({"code": self.code, "reason": self.reason})
        return data