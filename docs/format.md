# Recovered format and implementation boundaries

## Evidence

The supplied archive contains KAExtract.exe (76,800 bytes) and a short .NET
prerequisite note. SHA-256 of the executable:
`418ba66d7be64a2cdfa4079a7c64ff141c9bc60ecc76e6aa7cd1a3b1719b7f60`.
Static inspection with ILSpy 9.1 recovered the extraction behavior without
executing the program. Decompiled source and original assets are not distributed.

Its `ExportFile` routine searches for `FF D8 FF E0 00 10 4A 46 49 46`
(JPEG SOI and JFIF APP0). It copies bytes until `97 7F FF D9` or end of input,
then returns after the first match. Its assignments leave byte 3 zero, shift
several header bytes, and overwrite an earlier byte. These artifacts should
not be reproduced. The final `FF D9` is JPEG EOI; the preceding two bytes are
image data, not a general end signature. The routine does not decrypt, decompress,
or interpret an Xbox filesystem.

## Independent extraction

The replacement searches for SOI, walks length-delimited JPEG segments, reads
frame dimensions, and follows scan data with byte stuffing and restart markers
until EOI. Segment contents may themselves contain SOI/EOI (e.g. EXIF thumbnails),
so blindly taking the first EOI is incorrect. Multiple scans and multiple
separate JPEGs are supported. Only complete streams with a frame and scan are
returned; pixel decoding is a separate verification step. Output is the exact
source byte range, without re-encoding, header repair, or recompression. The desktop
option described below can subsequently add filename-derived EXIF metadata.

Known supported inputs: exported individual Kinect Adventures photo save files,
including extensionless `PM9_*` files inside `Content/.../4D5308ED/00000001`.
A local backup provided real CON packages containing 480 x 544 JPEGs starting
at offset 53,328 (`0xD050`). This is an observation, not a hardcoded offset.
Acceptance on 2026-10-22: the production Python CLI scanned 543 Kinect-related
backup files, recovered 511 JPEGs, skipped 32 non-photo files and reported no
input failures. Every recovered JPEG decoded with Pillow and matched its exact
source range; all were 480 x 544. Personal data and outputs remain local.

This is **contiguous JPEG carving**, not an STFS/FATX parser. It does not verify
Xbox signatures, reconstruct fragmented files, read raw USB disk images, or
decode animated `SouvenirRecording` files. Other games and arbitrary containers
are not verified. A structurally complete JPEG may still have damaged pixels.
False candidates are counted and skipped. There is no assertion that every
embedded JPEG in an arbitrary file is a Kinect photo.

## Automatic desktop discovery

The wxPython desktop app takes an input folder and output folder. It walks the full
input tree automatically, pruning links/junctions and the output subtree. A file
is a candidate when its name starts with `PM9_` (case-insensitive), or it has a
`CON `, `LIVE`, or `PIRS` header and title ID `4D5308ED` at offset `0x360`.
That title-ID field was checked in the supplied backup's actual photo packages.
Known `GameProgress` and `SouvenirRecording*` names are excluded. Other games'
embedded artwork and arbitrary ordinary JPGs are not selected automatically.
The original program uses a multiple-file chooser; recursive discovery is new.

Desktop acceptance scanned 608 files from the main backup folder, discovered
521 candidates, and recovered the same 511 exact-source, decodable JPGs with
no failures. Ten title-matched non-photo packages were skipped. A rerun recovered
zero new images and recognized all 511 existing outputs. The interactive catalog
also found all 511 photos and parsed filename dates for every one. Dates include
incorrect-looking console-clock years, so they are explicitly labelled rather
than asserted to be verified capture times. Selected export was checked against
exact source bytes. Windows GUI integration tests use a real wx event loop and
native controls with synthetic files to exercise scan, preview, checkbox events,
bulk selection, range selection, and selected export. These tests do not simulate
physical mouse input through the operating system.

Sorting is a view over immutable catalog indices: checks, Shift range anchors and
focused photo identity survive both column orders. Dates sort by their displayed
wall-clock values because console filename dates have no known timezone; unknown
dates stay last. Space toggles the focused checkbox explicitly in the virtual list.
Preview captions contain only the filename. Help owns export guidance and About;
the idle export button remains hoverable to explain missing prerequisites. An
early click opens a warning; a missing export-folder field turns red and returns
to its native colour when a folder is chosen. The metadata checkbox shares the
bottom action row immediately before Details.

Recovered JPGs retain source names with portable character sanitization.
Duplicate names get suffixes; exact matching output bytes are reused on reruns.
Fully written temporary files are published without replacement: Windows uses
exclusive rename and POSIX uses an exclusive hard link. POSIX output filesystems
must support hard links. Force termination may leave an uncommitted `.tmp` file;
existing JPGs are never treated as successfully saved until publication succeeds.

The desktop report contains per-file results with relative source locations,
dimensions, offsets, byte lengths, rejected-candidate counts, and failures.
Discovery retains at most 200 error locations and a full error count. No absolute
input root, image bytes, credentials or telemetry are persisted in the report.
Each run writes a new report filename rather than overwriting previous reports.
If report writing fails, the UI reports failure and preserves completed JPGs.
There is no upload or crash-reporting backend. In-window progress and scan errors
are transient; the local JSON report is the retained extraction diagnostic artifact.
Unexpected worker failures retain a bounded function/line trace in the copyable
Details dialog, without source paths or arguments. A process crash before report
publication does not produce a report; completed JPGs remain available.

The GUI uses wxPython, Gooey's underlying toolkit, with an in-process background
worker. Progress and pending preview requests are coalesced into bounded slots;
stale preview results cannot replace the currently focused photo. Preview pixels
are decoded with Pillow separately from the exact-byte export path. No Gooey
worker subprocess or argument quoting workaround remains. Windows packaging uses
PyInstaller's console bootloader with `hide_console='hide-early'` so command-line
invocations retain stdout without leaving a console on screen for desktop users.
Arguments invoke the headless folder workflow; no arguments open the GUI. Git
identity is injected internally by the build spec; About shows the release version,
author, and repository link without a commit suffix.

## Optional filename capture metadata

The desktop checkbox **Embed photo date** defaults on. Only valid filename dates
qualify; modified-file timestamps and unknown dates do not. Unchecked exports,
the folder CLI, ZIP CLI, and `recover_selection`'s default remain byte-exact.
`recover_selection(..., embed_dates=True)` enables the same transformation as the UI.

`capture_metadata.embed_capture_date` inserts or updates a header APP1 EXIF
segment, leaving the remaining JPEG bytes untouched, including all compressed
scans. The EXIF fields are IFD0 DateTime plus ExifIFD DateTimeOriginal and
DateTimeDigitized, with SubSecTime, SubSecTimeOriginal and SubSecTimeDigitized.
No timezone is inferred; existing UTC offset tags for these dates are removed.
Tag definitions follow [CIPA EXIF](https://www.cipa.jp/std/documents/e/DC-008-2010_E.pdf).

Existing TIFF data is kept at its original offsets; replacement directories are
appended and only the TIFF root pointer is changed. This preserves thumbnail
links, GPS data, opaque MakerNote bytes and other old directory entries. Both
TIFF byte orders are supported. Pillow's `Exif.tobytes` was inspected and does
not retain thumbnail IFD chains, so it is not used to rewrite existing EXIF.
Duplicate header EXIF segments, invalid directory bounds and a final APP1 payload
over 65,533 bytes fail explicitly before publishing that photo. The UI explains
how to recover the original by unchecking the option. This is a bounded date
editor, not a general EXIF repair tool.

Reports retain original source `offset`/`length`, plus `saved_length`,
`metadata_embedded` and an unzoned `capture_date` when applicable. Identical settings
produce identical bytes and safe reruns; changing settings may produce a numbered
copy. Source snapshots and all atomic publication/cancellation rules still apply.
Tests verify tags through Pillow, unchanged decoded pixels and non-EXIF bytes,
existing metadata/thumbnail offsets in both byte orders, fallback/disabled paths,
malformed input, bounded random metadata and repeat exports.

## Photo catalog and selection API

`catalog.scan_folder` inventories complete JPEG ranges before export and records
source SHA-256 snapshots. `read_photo` and `recovery.recover_selection` reject a
changed source rather than using stale offsets. Export accepts checked catalog
indices, preserves each image's original ordinal in multi-image files, and
uses the same atomic publication and collision rules as whole-folder recovery.
Cancellation stops between files/images and saves an honest partial report.

The catalog prefers dates encoded in `PM9_<player>_<year>_<month>_<day>_<hour>_<minute>_<second>_<millisecond>`
filenames. These reflect the console clock, not independently verified capture
times. Invalid or missing name dates fall back to the file-modified timestamp,
with distinct provenance; a copied backup's modification date can differ from
the photo date. Invented dates are never substituted. Catalogs contain at most
20,000 photos; input sizes and individual JPEG limits remain unchanged.

## Optional ZIP CLI

The JPEG parser returns immutable photo ranges and a rejected-candidate count. CLI input
directories require `--recursive`. Duplicate paths are read once. ZIP entries
have bounded ASCII names prefixed with source/image sequence numbers to avoid
collisions and path traversal. `manifest.json` records basenames, dimensions,
offsets, byte lengths, rejected candidates, skipped inputs and errors. It never
records absolute source paths or image bytes. It is included only in the local
ZIP; there are no telemetry or log uploads.

Maximum input file size is 128 MiB, maximum recovered images per file is 10,000,
and JPEG marker processing has a linear work budget. Inputs are read sequentially.
Output destinations are exclusive: an existing ZIP is never overwritten, and a
failed/cancelled write is removed. Exit codes: 0 = photos recovered without read
or limit errors (non-photo files may be skipped); 1 = invocation/output failure
or no photos; 2 = completed ZIP with some input failures; 130 = interrupted.

The implementation and documentation are MIT licensed. That license covers
only this project's new code, not the original executable or Microsoft's assets.
