import http
import typing
import warnings
from datetime import datetime
from exceptions.base import BermoidBaseException

__all__ = (
    "HTTPException",
)


class HTTPException(BermoidBaseException):
    def __init__(
        self,
        status_code: int,
        detail: typing.Optional[str] = None,
        headers: typing.Optional[dict[str, str]] = None,
        *,
        reason: typing.Optional[str] = None,
        timestamp: typing.Optional[datetime] = None,
        extra: typing.Optional[dict[str, typing.Any]] = None,
    ) -> None:
        if not isinstance(status_code, int) or not (100 <= status_code <= 599):
            warnings.warn(f"Invalid HTTP status code: {status_code!r}")
            status_code = 500
        detail = detail or http.HTTPStatus(status_code).phrase
        reason = reason or http.HTTPStatus(status_code).description
        headers = headers or {}
        timestamp = timestamp or datetime.utcnow()
        self.status_code = status_code
        self.detail = detail
        self.reason = reason
        self.headers = headers
        super().__init__(detail, code=str(status_code), extra=extra, timestamp=timestamp)

    def as_dict(self) -> dict[str, typing.Any]:
        data = super().as_dict()
        data.update(
            {
                "status_code": self.status_code,
                "detail": self.detail,
                "reason": self.reason,
                "headers": self.headers,
            }
        )
        return data

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(status_code={self.status_code}, detail={self.detail!r})"

    def __str__(self) -> str:
        return f"[{self.status_code}] {self.detail}"

    def with_headers(self, **extra: str) -> "HTTPException":
        new_headers = {**self.headers, **extra}
        return self.__class__(
            status_code=self.status_code,
            detail=self.detail,
            headers=new_headers,
            reason=self.reason,
        )
