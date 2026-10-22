"""Public app identity; build metadata stays out of normal user-facing labels."""

from dataclasses import dataclass
from importlib.metadata import version


@dataclass(frozen=True)
class AppIdentity:
    version: str
    author: str = 'NightMean'
    repository: str = 'https://github.com/NightMean/kinect-adventures-photo-extractor'


def app_identity() -> AppIdentity:
    return AppIdentity(version('kinect-adventures-photo-extractor'))
