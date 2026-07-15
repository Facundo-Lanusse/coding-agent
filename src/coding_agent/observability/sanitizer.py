"""Central redaction and payload limiting applied before every adapter."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

REDACTED = "[REDACTED]"
CONTENT_DISABLED = "[CONTENT_CAPTURE_DISABLED]"
TRUNCATED = "...[TRUNCATED]"

_SENSITIVE_KEY = re.compile(
    r"(?:^|[-_])(?:api[-_]?key|authorization|cookie|credential|password|"
    r"private[-_]?key|secret|access[-_]?token|auth[-_]?token|refresh[-_]?token|token)"
    r"(?:$|[-_])",
    re.IGNORECASE,
)
_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)


class Sanitizer:
    def __init__(
        self,
        *,
        max_payload_chars: int = 20_000,
        capture_content: bool = True,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        if max_payload_chars < 128:
            raise ValueError("Observability payload limit must be at least 128 characters.")
        self._max_payload_chars = max_payload_chars
        self._capture_content = capture_content
        source = os.environ if environment is None else environment
        self._environment_values = tuple(
            sorted(
                {value for key, value in source.items() if value and _SENSITIVE_KEY.search(key)},
                key=len,
                reverse=True,
            )
        )

    def sanitize(self, value: object) -> object:
        """Convert to JSON-compatible data, redact secrets, then enforce one payload cap."""

        sanitized = self._walk(value)
        serialized = json.dumps(sanitized, sort_keys=True, default=str)
        if len(serialized) <= self._max_payload_chars:
            return sanitized
        return serialized[: self._max_payload_chars - len(TRUNCATED)] + TRUNCATED

    def content(self, value: object) -> object:
        if not self._capture_content and value is not None:
            return CONTENT_DISABLED
        return self.sanitize(value)

    def _walk(self, value: object) -> object:
        if isinstance(value, BaseModel):
            return self._walk(value.model_dump(mode="json"))
        if isinstance(value, Enum):
            return self._walk(value.value)
        if isinstance(value, Path):
            return self._redact_string(str(value))
        if isinstance(value, Mapping):
            clean: dict[str, object] = {}
            for raw_key, item in value.items():
                key = str(raw_key)
                clean[key] = REDACTED if _SENSITIVE_KEY.search(key) else self._walk(item)
            return clean
        if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
            return [self._walk(item) for item in value]
        if isinstance(value, str):
            return self._redact_string(value)
        if value is None or isinstance(value, bool | int | float):
            return value
        return self._redact_string(str(value))

    def _redact_string(self, value: str) -> str:
        result = value
        for secret in self._environment_values:
            result = result.replace(secret, REDACTED)
        for pattern in _SENSITIVE_VALUE_PATTERNS:
            result = pattern.sub(REDACTED, result)
        return result
