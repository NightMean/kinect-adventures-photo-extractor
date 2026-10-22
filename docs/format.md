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

## Output and limits

Python returns immutable photo ranges and a rejected-candidate count. CLI input
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
