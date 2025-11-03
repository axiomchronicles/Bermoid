from __future__ import annotations

import json
import secrets
import gzip
import io
from typing import Optional, List, Union, Callable, Any, Dict
from datetime import datetime, timedelta

from wrappers.http_status import HTTP_STATUS_PHRASE
from exceptions.http import HTTPException  


class HTTPStatus:
    def __init__(self, code: int, phrase: str):
        self.code = code
        self.phrase = phrase

    def __str__(self):
        return f"{self.code} {self.phrase}"


class Response:
    def __init__(
        self,
        content: Union[str, bytes, Callable, None] = None,
        status_code: int = 200,
        headers: Optional[Dict[str, str]] = None,
        content_type: str = "text/plain",
        compress: bool = False,
    ):
        self.status_code = status_code
        self.headers = headers or {}
        self.content_type = content_type
        self.content = content
        self.streaming = callable(content)
        self.compress = compress
        self.encoding = "utf-8"

    async def __call__(self, scope, receive, send):
        try:
            response_headers = {
                b"Content-Type": f"{self.content_type}; charset={self.encoding}".encode(),
                **{
                    (k.encode() if isinstance(k, str) else k): (
                        v.encode() if isinstance(v, str) else v
                    )
                    for k, v in self.headers.items()
                },
            }

            content_length = 0
            if self.content:
                if isinstance(self.content, str):
                    content_length = len(self.content.encode(self.encoding))
                elif isinstance(self.content, bytes):
                    content_length = len(self.content)
                elif callable(self.content):
                    content_length = await self.get_stream_content_length(scope, receive, send)

            response_headers[b"Content-Length"] = str(content_length).encode()

            await send(
                {
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": list(response_headers.items()),
                }
            )

            if self.compress:
                if self.streaming:
                    await self._send_streaming_response_compressed(scope, receive, send)
                else:
                    await self._send_standard_response_compressed(send)
            else:
                if self.streaming:
                    await self._send_streaming_response(scope, receive, send)
                else:
                    await self._send_standard_response(send)

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def _send_streaming_response_compressed(self, scope, receive, send):
        try:
            if callable(self.content):
                gzip_buffer = io.BytesIO()
                gzip_stream = gzip.GzipFile(fileobj=gzip_buffer, mode="w")

                async for chunk in self.content(scope, receive, send):
                    gzip_stream.write(chunk)
                    gzip_stream.flush()
                    await send(
                        {
                            "type": "http.response.body",
                            "body": gzip_buffer.getvalue(),
                            "more_body": True,
                        }
                    )
                    gzip_buffer.truncate(0)
                    gzip_buffer.seek(0)

                gzip_stream.close()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Gzip stream error: {e}")

    async def _send_standard_response_compressed(self, send):
        try:
            if self.content is not None:
                body = (
                    self.content.encode(self.encoding)
                    if isinstance(self.content, str)
                    else self.content
                    if isinstance(self.content, bytes)
                    else json.dumps(self.content).encode(self.encoding)
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": gzip.compress(body),
                    }
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Compression failed: {e}")

    async def _send_streaming_response(self, scope, receive, send):
        try:
            if self.content:
                async for chunk in self.content(scope, receive, send):
                    await send(
                        {
                            "type": "http.response.body",
                            "body": chunk.encode(self.encoding)
                            if isinstance(chunk, str)
                            else chunk,
                            "more_body": True,
                        }
                    )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Streaming failed: {e}")

    async def _send_standard_response(self, send):
        try:
            if self.content is not None:
                body = (
                    self.content.encode(self.encoding)
                    if isinstance(self.content, str)
                    else self.content
                    if isinstance(self.content, bytes)
                    else json.dumps(self.content).encode(self.encoding)
                )
                await send({"type": "http.response.body", "body": body})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Response send error: {e}")

    async def get_stream_content_length(self, scope, receive, send) -> int:
        try:
            total = 0
            async for chunk in self.content(scope, receive, send):
                total += len(chunk.encode(self.encoding)) if isinstance(chunk, str) else len(chunk)
            return total
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Content length calc error: {e}")

    async def set_cookie(
        self,
        key: str,
        value: str,
        max_age: int = None,
        expires: Optional[Union[int, datetime]] = None,
        path: str = "/",
        domain: Optional[str] = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: Optional[str] = None,
    ):
        try:
            cookie_parts = [f"{key}={value}"]
            if max_age:
                cookie_parts.append(f"Max-Age={max_age}")
            if expires:
                if isinstance(expires, int):
                    expires = datetime.now() + timedelta(seconds=expires)
                cookie_parts.append(f"Expires={expires.strftime('%a, %d %b %Y %H:%M:%S GMT')}")
            if path:
                cookie_parts.append(f"Path={path}")
            if domain:
                cookie_parts.append(f"Domain={domain}")
            if secure:
                cookie_parts.append("Secure")
            if httponly:
                cookie_parts.append("HttpOnly")
            if samesite:
                cookie_parts.append(f"SameSite={samesite}")

            self.headers["Set-Cookie"] = "; ".join(cookie_parts)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Cookie set failed: {e}")

    async def delete_cookie(self, key: str):
        try:
            expires = datetime(1970, 1, 1).strftime("%a, %d %b %Y %H:%M:%S GMT")
            self.headers["Set-Cookie"] = f"{key}=; Expires={expires}; Max-Age=0; Path=/"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Cookie delete failed: {e}")

    async def json(self, content: Any, status_code: int = 200):
        try:
            self.content_type = "application/json"
            self.status_code = status_code
            self.content = content
            self.streaming = False
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"JSON response failed: {e}")

    async def stream(self, content: Union[str, bytes, Callable] = None):
        try:
            self.streaming = True
            if content:
                self.content = content
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Stream setup failed: {e}")

    @property
    def status_text(self):
        return f"{self.status_code} {HTTP_STATUS_PHRASE(self.status_code, 'Unknown')}"

    async def calculate_content_length(self):
        try:
            if self.content is None:
                return 0
            if isinstance(self.content, str):
                return len(self.content.encode(self.encoding))
            elif isinstance(self.content, bytes):
                return len(self.content)
            else:
                return len(json.dumps(self.content).encode(self.encoding))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Content length calc failed: {e}")
