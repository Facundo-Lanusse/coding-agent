"""Stable normalized fingerprints for progress and loop detection."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
from collections.abc import Mapping, Sequence
from pathlib import PurePath

_WHITESPACE = re.compile(r"\s+")
_MEMORY_ADDRESS = re.compile(r"0x[0-9a-fA-F]+")
_LONG_NUMBER = re.compile(r"\b\d{4,}\b")


class FingerprintFactory:
    @staticmethod
    def tool(
        name: str,
        arguments: Mapping[str, object],
        *,
        relevant_keys: Sequence[str] = (),
    ) -> str:
        selected = (
            {key: arguments[key] for key in relevant_keys if key in arguments}
            if relevant_keys
            else dict(arguments)
        )
        return _fingerprint("tool", {"name": name.casefold(), "arguments": selected})

    @staticmethod
    def command(command: str | Sequence[str]) -> str:
        argv = shlex.split(command) if isinstance(command, str) else list(command)
        normalized = [item.casefold().strip() for item in argv]
        return _fingerprint("command", normalized)

    @staticmethod
    def file_read(path: str | PurePath, content_digest: str) -> str:
        normalized_path = PurePath(path).as_posix().casefold()
        return _fingerprint(
            "file_read",
            {"path": normalized_path, "content_digest": content_digest.casefold()},
        )

    @staticmethod
    def error(code: str, message: str, *, command: str | Sequence[str] | None = None) -> str:
        normalized_message = _normalize_error(message)
        payload: dict[str, object] = {
            "code": code.casefold().strip(),
            "message": normalized_message,
        }
        if command is not None:
            payload["command"] = FingerprintFactory.command(command)
        return _fingerprint("error", payload)

    @staticmethod
    def result(
        status: str,
        *,
        output_digest: str | None = None,
        error_fingerprint: str | None = None,
    ) -> str:
        return _fingerprint(
            "result",
            {
                "status": status.casefold().strip(),
                "output_digest": output_digest,
                "error_fingerprint": error_fingerprint,
            },
        )

    @staticmethod
    def progress(evidence_ids: Sequence[str], change_ids: Sequence[str]) -> str:
        return _fingerprint(
            "progress",
            {
                "evidence_ids": sorted(set(evidence_ids)),
                "change_ids": sorted(set(change_ids)),
            },
        )


def _fingerprint(kind: str, payload: object) -> str:
    serialized = json.dumps(
        {"kind": kind, "payload": _normalize(payload)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def _normalize(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, str):
        return _WHITESPACE.sub(" ", value.strip()).casefold()
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _normalize_error(message: str) -> str:
    normalized = _WHITESPACE.sub(" ", message.strip()).casefold()
    normalized = _MEMORY_ADDRESS.sub("<address>", normalized)
    return _LONG_NUMBER.sub("<number>", normalized)
