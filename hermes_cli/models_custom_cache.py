"""Coalesce cold custom-endpoint catalogs while preserving profile isolation.

The models facade owns cache storage and remains the import/monkeypatch surface.
Only callers of the same profile and credential wait on each other's live probe.
"""

from __future__ import annotations

import threading
import time
import weakref

# Weak values release idle locks after the last caller, including rotated credentials.
_fetch_locks: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def fetch_cold_catalog(*, cache_key, fingerprint, ttl_seconds, force_refresh, stale_entry,
                       fetch, encode, decode):
    from hermes_cli import models
    from hermes_cli.model_switch_providers import _NativePickerModelList

    lock_key = (str(models._provider_models_cache_path()), cache_key)
    with models._cache_write_lock:
        fetch_lock = _fetch_locks.get(lock_key)
        if fetch_lock is None:
            fetch_lock = threading.RLock()
            _fetch_locks[lock_key] = fetch_lock
    with fetch_lock:
        latest = models._load_provider_models_cache().get(cache_key)
        native = isinstance(latest, dict) and latest.get("native_catalog") is True
        if (not force_refresh and models._cache_entry_valid(latest, fingerprint, allow_empty=native)
                and time.time() - latest["at"] < ttl_seconds):
            return decode(latest)
        live = fetch()
        if live or isinstance(live, _NativePickerModelList):
            stored = encode(live)
            # Reload under the write lock, so another credential's completed probe survives.
            # Network I/O and reentrant discovery run outside this process-wide lock.
            with models._cache_write_lock:
                models._store_cache_entry(cache_key, stored)
            return decode(stored)
        # An offline endpoint can retain a non-empty catalog for the same credential.
        if models._cache_entry_valid(stale_entry, fingerprint):
            return decode(stale_entry)
        return models._chat_catalog_rows(live)
