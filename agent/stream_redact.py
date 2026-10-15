"""Prefix-stable egress filtering for incremental platform text.

Ordinary prose streams immediately except ambiguous credential prefixes. Once credential-shaped context is
seen, retain the rest of that semantic segment until completion, then run the
existing egress policy once. In particular, never publish a sequence of moving
head/tail masks from which a reader could reconstruct the secret. This does not
invent a new secret policy: URL exceptions and unrecognized credentials retain
the same limits as redact_for_egress. Future plugin registrations cannot retract
text already sent; plugins must register their patterns before streaming.
"""

from __future__ import annotations

import re

from agent import redact

# Names alone are safe, but retain their context before a later =/: can turn
# them into an assignment. This deliberately buffers prose discussing secrets.
_SENSITIVE_WORD = re.compile(r"\b[\w.-]*(?:api.?key|key|token|secret|password|passwd|pass|pw|credential|auth)[\w.-]*", re.IGNORECASE)


def _markers() -> tuple[tuple[str, bool], ...]:
    # Same profile-scoped registry and plugin prefix policy as the final scrub.
    with redact._VAULT_REDACTION_LOCK:
        values = tuple(redact._VAULT_REDACTION_VALUES.get(redact._vault_scope(), ()))
    # Prefix patterns have a left word boundary; JWT/vault matching does not.
    return (*((value, True) for value in redact._PREFIX_SUBSTRINGS),
            ("-----BEGIN", False), ("eyJ", False), *((value, False) for value in values))


def _marker_boundary(text: str, index: int, bounded: bool) -> bool:
    return not bounded or index == 0 or not (text[index - 1].isalnum() or text[index - 1] in "_-")


def _pending_marker(text: str, marker: str, bounded: bool) -> tuple[int, bool]:
    start = 0
    while (found := text.find(marker, start)) >= 0:
        if _marker_boundary(text, found, bounded):
            return found, True
        start = found + 1
    for size in range(min(len(marker) - 1, len(text)), 0, -1):
        start = len(text) - size
        if text.endswith(marker[:size]) and _marker_boundary(text, start, bounded):
            return start, False
    return len(text), False


def _unprefixed_tail(text: str) -> int:
    # The final policy's unprefixed numeric/token shapes need future context.
    # Zhipu's >=49-character shape always preserves its first six characters.
    candidate = re.search(r"(?<![A-Za-z0-9_.-])[0-9a-f]{7,32}(?:\.[A-Za-z0-9]*)?$", text)
    if candidate:
        return candidate.start() + 6
    phone = re.search(r"\+[1-9]?[0-9]*$", text)
    return phone.start() if phone else len(text)


class StreamingEgressRedactor:
    """Release only unchanged, unambiguous prose prefixes; scrub the held suffix once."""

    def __init__(self) -> None:
        self._raw = ""
        self._published = ""
        self._blocked = False

    def feed(self, delta: str) -> str:
        self._raw += delta
        if self._blocked:
            return ""
        text = self._raw
        end = len(text)
        for marker, bounded in _markers():
            position, complete = _pending_marker(text, marker, bounded)
            end = min(end, position)
            self._blocked |= complete
        # Bearer replacement normalizes casing, so retain the scheme as well.
        position, complete = _pending_marker(text.lower(), "bearer", True)
        end = min(end, position)
        self._blocked |= complete
        sensitive = _SENSITIVE_WORD.search(text)
        if sensitive:
            end = min(end, sensitive.end())
            self._blocked = True
        # URL userinfo and Telegram bot-token suffixes must not be sent before
        # a later @/token-length boundary makes the final policy recognize them.
        for pattern in (r"://", r"(?<!\d)\d{8,}:"):
            candidate = re.search(pattern, text)
            if candidate:
                end = min(end, candidate.end())
                self._blocked = True
        end = min(end, _unprefixed_tail(text))
        scrubbed = redact.redact_for_egress(text)
        if scrubbed != text:
            common = 0
            for original, safe in zip(text, scrubbed):
                if original != safe:
                    break
                common += 1
            end = min(end, common)
            self._blocked = True
        prefix = text[:end]
        if redact.redact_for_egress(prefix) != prefix:
            self._blocked = True
            return ""
        if not prefix.startswith(self._published):
            return ""
        ready = prefix[len(self._published):]
        self._published = prefix
        return ready

    def finish(self) -> str:
        text = redact.redact_for_egress(self._raw)
        if not text.startswith(self._published):
            # A future-context policy or a failed scrub must never release raw
            # retained bytes or rewrite an append-only platform's old prefix.
            return redact.REDACTION_UNAVAILABLE
        return text[len(self._published):]
