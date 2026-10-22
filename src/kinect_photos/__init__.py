"""Lossless, dependency-free extraction of embedded JPEG photo streams."""

from .jpeg import Photo, ScanResult, scan_jpegs

__all__ = ["Photo", "ScanResult", "scan_jpegs"]
