"""Text boundaries shared by native Slack stream finalization and recovery."""

def stream_relation(sent: str, text: str) -> tuple[str, str]:
    """Classify turn-final ``text`` against the streamed ``sent``: ``("equal", "")`` — the
    streamed message already shows the whole final; ``("extends", delta)`` — the final
    continues it, ``delta`` being the exact raw tail still to append; ``("unrelated", "")`` —
    not this stream's final (interim commentary, a rewritten answer, an empty stream).

    The agent strips its final response and appends footers with ``rstrip()``, so the final
    may differ from the streamed frames by surrounding whitespace only. The delta is sliced
    from the RAW ``text`` where the streamed core ends — never from a normalized copy — so
    nothing inside the answer (blank lines, fences, tables) is dropped or repeated."""
    core = sent.strip()
    if not core:
        return "unrelated", ""
    if text.startswith(sent):
        delta = text[len(sent):]
        return ("extends" if delta else "equal"), delta
    lead = len(text) - len(text.lstrip())
    if text[lead:].startswith(core):
        delta = text[lead + len(core):]
        return ("extends" if delta.strip() else "equal"), delta
    return "unrelated", ""


def continuation_offset(text: str, sent: str) -> int:
    """A new message repeats a split word whole; an append remains byte-exact."""
    cut = len(sent)
    if cut < len(text) and cut and not text[cut].isspace() and not text[cut - 1].isspace():
        boundary = max(text.rfind(" ", 0, cut), text.rfind("\n", 0, cut))
        return boundary + 1
    return cut
