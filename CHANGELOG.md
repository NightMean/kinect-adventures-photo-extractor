# Changelog

All notable changes to Kinect Adventures Photo Extractor are documented here.

## [1.0.0] - 2026-10-23

First stable release.

### Added

- Windows desktop app for scanning exported Xbox 360 folders and recovering
  Kinect Adventures! photos.
- Photo discovery, selection, previews, date sorting, progress reporting, and
  cancellation.
- Optional embedding of valid filename dates into JPEG EXIF metadata without
  recompressing the image.
- Python 3.10+ command-line extractor for creating ZIP archives.
- Recovery report describing saved, skipped, and failed files.
- In-app guide for copying Xbox 360 saves from newer USB storage and older
  FATX/XTAF-formatted drives.

### Limitations

- The app reads exported individual save files and folders, not raw USB or disk
  images.
- Older Xbox-formatted drives may require a separate storage browser to copy
  the save files to the computer first.
- Missing, fragmented, or incomplete JPEG data cannot be reconstructed.
