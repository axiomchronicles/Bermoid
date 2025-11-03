import typing

from exceptions.http.base import HTTPException

__all__ = (
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "MethodNotAllowed",
    "NotAcceptable",
    "RequestTimeout",
    "Conflict",
    "Gone",
    "UnsupportedMediaType",
    "UnprocessableEntity",
    "TooManyRequests",
    "InternalServerError",
    "NotImplemented",
    "BadGateway",
    "ServiceUnavailable",
    "GatewayTimeout",
)


class MethodNotAllowed(HTTPException):
    def __init__(
        self,
        allowed_methods: typing.Optional[list[str]] = None,
        detail: typing.Optional[str] = None,
        headers: typing.Optional[dict[str, str]] = None,
    ) -> None:
        allowed_methods = allowed_methods or []
        headers = headers or {}
        if allowed_methods:
            headers["Allow"] = ", ".join(sorted(set(allowed_methods)))
        detail = detail or "Method Not Allowed"
        super().__init__(status_code=405, detail=detail, headers=headers)

    def __str__(self) -> str:
        allow = self.headers.get("Allow", "N/A")
        return f"[405] {self.detail} | Allow: {allow}"

class BadRequest(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(400, detail or "Bad Request", headers)


class Unauthorized(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(401, detail or "Unauthorized", headers)


class Forbidden(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(403, detail or "Forbidden", headers)


class NotFound(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(404, detail or "Not Found", headers)


class NotAcceptable(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(406, detail or "Not Acceptable", headers)


class RequestTimeout(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(408, detail or "Request Timeout", headers)


class Conflict(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(409, detail or "Conflict", headers)


class Gone(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(410, detail or "Gone", headers)


class UnsupportedMediaType(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(415, detail or "Unsupported Media Type", headers)


class UnprocessableEntity(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(422, detail or "Unprocessable Entity", headers)


class TooManyRequests(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(429, detail or "Too Many Requests", headers)


class InternalServerError(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(500, detail or "Internal Server Error", headers)


class NotImplemented(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(501, detail or "Not Implemented", headers)


class BadGateway(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(502, detail or "Bad Gateway", headers)


class ServiceUnavailable(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(503, detail or "Service Unavailable", headers)


class GatewayTimeout(HTTPException):
    def __init__(self, detail: str | None = None, headers: dict | None = None) -> None:
        super().__init__(504, detail or "Gateway Timeout", headers)