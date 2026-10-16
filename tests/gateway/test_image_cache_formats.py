"""Raster attachments accepted by routing must survive the gateway cache (#119593)."""
import io
from pathlib import Path

import pytest
from PIL import Image

from gateway.platforms.base import cache_image_from_bytes


@pytest.mark.parametrize("format,extension", [("PNG", ".png"), ("JPEG", ".jpg"), ("HEIF", ".heic"), ("AVIF", ".avif"), ("TIFF", ".tiff")])
def test_real_raster_bytes_survive_cache(tmp_path, monkeypatch, format, extension):
    import pillow_heif

    pillow_heif.register_heif_opener()
    cache = tmp_path / "images"
    monkeypatch.setattr("gateway.platforms.base.IMAGE_CACHE_DIR", cache)
    data = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(data, format=format)
    cached = Path(cache_image_from_bytes(data.getvalue(), extension))
    assert cached.read_bytes() == data.getvalue()
    assert cached.parent == cache


@pytest.mark.parametrize("data", [b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"<html>error</html>", b"%PDF-1.7", b"\x00\x00\x00\x18ftypmp42", b"\x00\x00\x00\x18ftyp"])
def test_non_raster_and_non_image_containers_are_not_cached(tmp_path, monkeypatch, data):
    cache = tmp_path / "images"
    monkeypatch.setattr("gateway.platforms.base.IMAGE_CACHE_DIR", cache)
    with pytest.raises(ValueError, match="non-image data"):
        cache_image_from_bytes(data, ".jpg")
    assert not cache.exists()
