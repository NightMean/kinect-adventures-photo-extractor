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
source byte range, without re-encoding, header repair, or recompression.

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

The Gooey desktop app presents only input and output folders. It walks the full
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
zero new images and recognized all 511 existing outputs. The packaged GUI's
two folder controls were inspected through Windows accessibility. Its Start
button could not be exercised by the automation helper because window capture
timed out; the packaged worker was exercised directly instead.

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
There is no upload or crash-reporting backend. Gooey's in-window progress output
is transient; the local JSON report is the retained diagnostic artifact.

The GUI follows MotionPhoto2's Gooey integration. Gooey 1.0.8.1 imports `six`
without declaring it, so the GUI extra lists `six` explicitly. Windows packaging
uses PyInstaller's console bootloader with `hide_console='hide-early'` to keep
the progress pipe available without leaving a console window on screen.
The packaged worker runs with `--ignore-gooey`; that path must bypass opening
another configuration window. Git identity is injected by the build spec.
Gooey's Windows quote helper also mishandles trailing backslashes, including
drive roots. The app locally replaces its three quote bindings with Python's
standard Windows argument encoder. A regression test passes actual Gooey folder
formatting through a real shell-free child process with drive roots, trailing
separators, spaces, Unicode, and shell metacharacters.

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
