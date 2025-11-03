from exceptions.websocket.base import WebSocketException

__all__ = ("WebSocketClosed", "InvalidFrame", "PolicyViolation")

class WebSocketClosed(WebSocketException):
    def __init__(self, reason: str | None = None) -> None:
        super().__init__(1000, reason or "WebSocket Closed Normally")


class InvalidFrame(WebSocketException):
    def __init__(self, reason: str | None = None) -> None:
        super().__init__(1002, reason or "Protocol Error: Invalid Frame Received")


class PolicyViolation(WebSocketException):
    def __init__(self, reason: str | None = None) -> None:
        super().__init__(1008, reason or "Policy Violation")
