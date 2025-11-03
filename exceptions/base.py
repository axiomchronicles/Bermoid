import typing
import traceback
from datetime import datetime
import uuid

__all__ = ("BermoidBaseException",)


class BermoidBaseException(Exception):
    def __init__(
        self,
        message: typing.Optional[str] = None,
        *,
        code: typing.Optional[str] = None,
        extra: typing.Optional[dict[str, typing.Any]] = None,
        timestamp: typing.Optional[datetime] = None,
    ) -> None:
        self.id = uuid.uuid4().hex
        self.timestamp = timestamp or datetime.utcnow()
        self.code = code or self.__class__.__name__
        self.message = message or self.__class__.__name__
        self.extra = extra or {}
        super().__init__(self.message)

    def as_dict(self) -> dict[str, typing.Any]:
        return {
            "id": self.id,
            "code": self.code,
            "message": self.message,
            "extra": self.extra,
            "timestamp": self.timestamp.isoformat(),
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def traceback(self) -> str:
        return "".join(traceback.format_exception(type(self), self, self.__traceback__))
