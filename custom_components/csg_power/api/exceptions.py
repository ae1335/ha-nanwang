"""Exceptions raised by the CSG API client."""

from __future__ import annotations


class CSGAPIError(Exception):
    """Generic API error."""

    def __init__(self, sta: str, msg: str | None = None) -> None:
        super().__init__()
        self.sta = sta
        self.msg = msg

    def __str__(self) -> str:
        return f"<CSGAPIError sta={self.sta} message={self.msg}>"


class CSGHTTPError(CSGAPIError):
    """Unexpected HTTP status code (!=200)."""

    def __init__(self, code: int) -> None:
        super().__init__(f"HTTP{code}")
        self.status_code = code

    def __str__(self) -> str:
        return f"<CSGHTTPError code={self.status_code}>"


class InvalidCredentials(CSGAPIError):
    """Wrong username/password combination."""

    def __str__(self) -> str:
        return f"<CSGInvalidCredentials sta={self.sta} message={self.msg}>"


class NotLoggedIn(CSGAPIError):
    """Not logged in or login expired."""

    def __str__(self) -> str:
        return f"<CSGNotLoggedIn sta={self.sta} message={self.msg}>"


class QrCodeExpired(Exception):
    """QR code has expired."""
