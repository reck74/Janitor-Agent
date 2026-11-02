"""Fork-only helper that converts a PEP 440 version to Janitor's display form.

Janitor declares its version in ``pyproject.toml`` as ``<hermes>+janitor.N``
(PEP 440-valid); ``hermes_cli.version_info.get_version_info()`` reports it for
a checkout. The banner and CLI ``--version`` use a hyphen instead because
humans read ``0.22.5-janitor.1`` more naturally than ``0.22.5+janitor.1``.

This module is the only place that performs the character conversion. It
takes the raw string as input (rather than importing the canonical value)
so a test can call it deterministically without depending on import order.
"""
from __future__ import annotations


def display_version(raw: str) -> str:
    """Return the version suitable for end-user display.

    Conversion rule: the FIRST ``+`` in the version string is replaced
    with ``-``. Pre-release segments that legitimately use ``+`` in some
    PEP 440 contexts are not affected because Janitor versions never
    carry a pre-release segment.
    """
    return raw.replace("+", "-", 1)
