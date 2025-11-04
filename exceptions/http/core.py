import typing
from exceptions.http.base import HTTPException

__all__ = (
    "BadRequest",
    "Unauthorized",
    "PaymentRequired",
    "Forbidden",
    "NotFound",
    "MethodNotAllowed",
    "NotAcceptable",
    "ProxyAuthenticationRequired",
    "RequestTimeout",
    "Conflict",
    "Gone",
    "LengthRequired",
    "PreconditionFailed",
    "PayloadTooLarge",
    "RequestURITooLong",
    "UnsupportedMediaType",
    "RequestedRangeNotSatisfiable",
    "ExpectationFailed",
    "ImATeapot",
    "MisdirectedRequest",
    "UnprocessableEntity",
    "Locked",
    "FailedDependency",
    "UpgradeRequired",
    "PreconditionRequired",
    "TooManyRequests",
    "RequestHeaderFieldsTooLarge",
    "UnavailableForLegalReasons",
    "InternalServerError",
    "NotImplemented",
    "BadGateway",
    "ServiceUnavailable",
    "GatewayTimeout",
    "HTTPVersionNotSupported",
    "VariantAlsoNegotiates",
    "InsufficientStorage",
    "LoopDetected",
    "NotExtended",
    "NetworkAuthenticationRequired",
)


# --- 4xx Client Errors ---

class BadRequest(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(400, detail or "Bad Request", headers)


class Unauthorized(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(401, detail or "Unauthorized", headers)


class PaymentRequired(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(402, detail or "Payment Required", headers)


class Forbidden(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(403, detail or "Forbidden", headers)


class NotFound(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(404, detail or "Not Found", headers)


class MethodNotAllowed(HTTPException):
    def __init__(self, allowed_methods=None, detail=None, headers=None):
        allowed_methods = allowed_methods or []
        headers = headers or {}
        if allowed_methods:
            headers["Allow"] = ", ".join(sorted(set(allowed_methods)))
        detail = detail or "Method Not Allowed"
        super().__init__(405, detail, headers)

    def __str__(self):
        allow = self.headers.get("Allow", "N/A")
        return f"[405] {self.detail} | Allow: {allow}"


class NotAcceptable(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(406, detail or "Not Acceptable", headers)


class ProxyAuthenticationRequired(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(407, detail or "Proxy Authentication Required", headers)


class RequestTimeout(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(408, detail or "Request Timeout", headers)


class Conflict(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(409, detail or "Conflict", headers)


class Gone(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(410, detail or "Gone", headers)


class LengthRequired(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(411, detail or "Length Required", headers)


class PreconditionFailed(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(412, detail or "Precondition Failed", headers)


class PayloadTooLarge(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(413, detail or "Payload Too Large", headers)


class RequestURITooLong(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(414, detail or "Request-URI Too Long", headers)


class UnsupportedMediaType(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(415, detail or "Unsupported Media Type", headers)


class RequestedRangeNotSatisfiable(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(416, detail or "Requested Range Not Satisfiable", headers)


class ExpectationFailed(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(417, detail or "Expectation Failed", headers)


class ImATeapot(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(418, detail or "I'm a teapot", headers)


class MisdirectedRequest(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(421, detail or "Misdirected Request", headers)


class UnprocessableEntity(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(422, detail or "Unprocessable Entity", headers)


class Locked(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(423, detail or "Locked", headers)


class FailedDependency(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(424, detail or "Failed Dependency", headers)


class UpgradeRequired(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(426, detail or "Upgrade Required", headers)


class PreconditionRequired(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(428, detail or "Precondition Required", headers)


class TooManyRequests(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(429, detail or "Too Many Requests", headers)


class RequestHeaderFieldsTooLarge(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(431, detail or "Request Header Fields Too Large", headers)


class UnavailableForLegalReasons(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(451, detail or "Unavailable For Legal Reasons", headers)


# --- 5xx Server Errors ---

class InternalServerError(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(500, detail or "Internal Server Error", headers)


class NotImplemented(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(501, detail or "Not Implemented", headers)


class BadGateway(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(502, detail or "Bad Gateway", headers)


class ServiceUnavailable(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(503, detail or "Service Unavailable", headers)


class GatewayTimeout(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(504, detail or "Gateway Timeout", headers)


class HTTPVersionNotSupported(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(505, detail or "HTTP Version Not Supported", headers)


class VariantAlsoNegotiates(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(506, detail or "Variant Also Negotiates", headers)


class InsufficientStorage(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(507, detail or "Insufficient Storage", headers)


class LoopDetected(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(508, detail or "Loop Detected", headers)


class NotExtended(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(510, detail or "Not Extended", headers)


class NetworkAuthenticationRequired(HTTPException):
    def __init__(self, detail=None, headers=None):
        super().__init__(511, detail or "Network Authentication Required", headers)
