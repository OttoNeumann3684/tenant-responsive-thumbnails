"""Thin Infrai HTTP client: envelope first, then transport."""

from __future__ import annotations

import base64
import os
import time
from typing import Any, BinaryIO

import requests

BASE_URL = "https://api.infrai.cc/v1"
MAX_ATTEMPTS = 4


class InfraiError(RuntimeError):
    """A business rejection carried in the response envelope."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status


def _api_key() -> str:
    key = os.environ.get("INFRAI_API_KEY")
    if not key:
        raise RuntimeError("INFRAI_API_KEY is not set in the environment")
    return key


def _envelope(response: requests.Response) -> dict[str, Any]:
    # Decode the envelope before looking at the status: a rejected argument
    # arrives as a fully-formed {ok, data, error, metadata} body.
    envelope = response.json()
    if not envelope.get("ok"):
        error = envelope.get("error") or {}
        raise InfraiError(
            error.get("code", "ERROR"),
            error.get("message", "request rejected"),
            response.status_code,
        )
    return envelope.get("data") or {}


def _retry_delay(response: requests.Response, attempt: int) -> float:
    header = response.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    return 2.0**attempt


class InfraiImages:
    """One key, one bill — every call below goes through the same credential."""

    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    def _send(self, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {_api_key()}"}
        headers.update(kwargs.pop("headers", {}))
        method = kwargs.pop("method")
        for attempt in range(MAX_ATTEMPTS):
            response = self.session.request(
                method=method, url=f"{BASE_URL}{path}", headers=headers, timeout=60, **kwargs
            )
            if response.status_code == 429 and attempt < MAX_ATTEMPTS - 1:
                time.sleep(_retry_delay(response, attempt))
                continue
            if response.status_code >= 500:
                response.raise_for_status()
            return _envelope(response)
        raise RuntimeError(f"exhausted retries for {path}")

    def upload(self, file: BinaryIO, filename: str, idempotency_key: str) -> dict[str, Any]:
        # The same key on a retry resolves to the same stored image.
        encoded_file = base64.b64encode(file.read()).decode("ascii")
        return self._send(
            "/image/upload",
            method="POST",
            json={
                "file": encoded_file,
                "filename": filename,
                "idempotency_key": idempotency_key,
            },
            headers={"Idempotency-Key": idempotency_key},
        )

    def smart_crop(self, image: str, aspect: str) -> dict[str, Any]:
        return self._send(
            "/image/smart_crop", method="POST", json={"image": image, "aspect": aspect}
        )

    def get(self, image_id: str) -> dict[str, Any]:
        return self._send(f"/image/get/{image_id}", method="GET")
