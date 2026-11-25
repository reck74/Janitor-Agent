"""The early ``janitor update`` path prints its banner on any console encoding.

On Windows a redirected stdout is cp1252 and cannot encode «🔥 → ✓»; the
launcher repairs the stream before printing (directive #13 keeps that path
free of heavy imports). The stream is passed as data, so this holds on any OS.
"""

from __future__ import annotations

import io

from janitor.stdio import utf8_stream


def test_a_cp1252_stream_prints_the_banner_glyphs_as_utf8():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")

    fixed = utf8_stream(stream)
    print("🔥 → ✓ ✗ actualización", file=fixed)
    fixed.flush()

    assert raw.getvalue().decode("utf-8") == "🔥 → ✓ ✗ actualización\n"


def test_a_stream_without_reconfigure_is_left_usable():
    class Opaque:
        encoding = "ascii"

        def write(self, text):
            return len(text)

    stream = Opaque()

    assert utf8_stream(stream) is stream
    assert utf8_stream(None) is None
