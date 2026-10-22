"""Decode a bounded, disposable preview without changing the exported JPEG."""

from dataclasses import dataclass
from io import BytesIO
import warnings

from .catalog import PhotoEntry, read_photo

MAX_PREVIEW_PIXELS = 25_000_000
MAX_PREVIEW_EDGE = 1200


@dataclass(frozen=True)
class PreviewPixels:
    width: int
    height: int
    rgb: bytes


def decode_preview(entry: PhotoEntry) -> PreviewPixels:
    from PIL import Image, UnidentifiedImageError

    if entry.image.width * entry.image.height > MAX_PREVIEW_PIXELS:
        raise ValueError('preview_too_large')
    data = read_photo(entry)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > MAX_PREVIEW_PIXELS:
                    raise ValueError('preview_too_large')
                image.thumbnail((MAX_PREVIEW_EDGE, MAX_PREVIEW_EDGE), Image.Resampling.LANCZOS)
                rgb = image.convert('RGB')
                return PreviewPixels(rgb.width, rgb.height, rgb.tobytes())
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('preview_unavailable') from exc
