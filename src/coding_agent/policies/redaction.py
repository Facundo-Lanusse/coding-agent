"""Central redaction for policy records and approval prompts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

REDACTED = "[REDACTED]"
_SENSITIVE_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "private_key",
    "secret",
    "token",
)


def redact_arguments(
    arguments: Mapping[str, object],
    *,
    sensitive_keys: frozenset[str] = frozenset(),
) -> dict[str, object]:
    """Return a recursively sanitized copy suitable for logs and decisions."""

    sanitized: dict[str, object] = {}
    for key, value in arguments.items():
        if key in sensitive_keys or _is_sensitive_key(key):
            sanitized[key] = REDACTED
        elif key == "argv" and isinstance(value, Sequence) and not isinstance(value, str):
            sanitized[key] = _redact_argv(value)
        else:
            sanitized[key] = _redact_value(value, sensitive_keys=sensitive_keys)
    return sanitized


def _redact_value(value: object, *, sensitive_keys: frozenset[str]) -> object:
    if isinstance(value, Mapping):
        nested: dict[str, object] = {}
        for key, item in value.items():
            text_key = str(key)
            if text_key in sensitive_keys or _is_sensitive_key(text_key):
                nested[text_key] = REDACTED
            else:
                nested[text_key] = _redact_value(item, sensitive_keys=sensitive_keys)
        return nested
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_redact_value(item, sensitive_keys=sensitive_keys) for item in value]
    return value


def _redact_argv(values: Sequence[object]) -> list[object]:
    redacted: list[object] = []
    hide_next = False
    for value in values:
        if not isinstance(value, str):
            redacted.append(value)
            continue
        if hide_next:
            redacted.append(REDACTED)
            hide_next = False
            continue
        option, separator, _ = value.partition("=")
        if option.startswith("-") and _is_sensitive_key(option.lstrip("-").replace("-", "_")):
            if separator:
                redacted.append(f"{option}={REDACTED}")
            else:
                redacted.append(option)
                hide_next = True
            continue
        redacted.append(value)
    return redacted


def _is_sensitive_key(key: str) -> bool:
    normalized = key.casefold()
    return any(marker in normalized for marker in _SENSITIVE_MARKERS)
