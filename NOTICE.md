# NOTICE

This product is derived from an existing open-source project. MIT requires that
the original copyright notice and permission notice be retained; this file
records what came from where, and what was changed.

## Original work

- **Project:** songup — *Party jukebox queue: guests add songs, the host screen plays them*
- **Source:** https://github.com/motz0815/songup
- **Licence:** MIT
- **Copyright:** the songup authors

The `LICENSE` file in this repository is reproduced verbatim and unmodified.

## This version

- **Project:** SongStub · 曲票 (repository name: `songup-queue`)
- **Version:** 2.1.0
- **Copyright (C) 2026** the SongStub contributors
- **Licence:** MIT

## Relationship to the original

The original project established the product idea: a QR code on the host
screen, guests add songs from their phones, the host plays them. This
repository keeps that idea and is an independent implementation — no source
file from the original is copied verbatim.

The name **SongUp** refers to the upstream project. **SongStub / 曲票** is the
name of this version and does not claim to be the official upstream release.

## Statement of changes

### Rewritten relative to the original

| Area | Change |
|---|---|
| Queue engine (`queue_engine.py`) | Occupancy-based quota (a playing song still holds a slot), dedup that covers the currently playing track, cooldown recorded against the song that actually finished, `seq` playback serial, explicit `queue` / `fallback` / `empty` source state |
| Guest page (`templates/guest.html`) | Rebuilt on the ticket-stub visual language; quota rendered as physical ticket slots; DOM built with `createElement` + `textContent` only |
| Host page (`templates/host.html`) | Rebuilt as the dark "stage" surface; torn-ticket now-playing card; QR join card; progress bar and remaining time for local media; keyboard shortcuts |
| Screenshot tooling (`verify/docs-shot.cjs`) | Rewritten to seed state through the real API and to keep third-party video frames out of the repo |

### Added in this version

| File | Purpose |
|---|---|
| `qrmini.py` | Dependency-free QR encoder (byte mode, ECC-M, versions 1–10) |
| `tools/verify_qr.py` | Differential test of `qrmini` against the reference `qrcode` library |
| `tools/make_brand.py` | Generates every brand asset (mark, wordmark, favicon, social card) |
| `tools/make_diagram.py` | Generates `docs/design/ticket-flow.png` |
| `tools/make_zip.py` | Builds and verifies the release archive |
| `verify/responsive.cjs` | Responsive, contrast, external-request and reduced-motion gate |
| `tests/test_qrmini.py` | Golden-matrix and structure tests for the encoder |
| `docs/design/DESIGN.md` | Palette, typography, graphic language, interaction list, acceptance criteria |
| `docs/brand/*` | Logo mark, wordmark, favicon, social card |
| `static/favicon.svg` | Served favicon (same file as `docs/brand/favicon.svg`) |

### Assets

All visual assets in `docs/brand/` and `docs/design/` are original geometric
drawings produced by the scripts in `tools/`. No third-party artwork, icon set,
font file or photograph is included. Screenshots contain only the repository's
own ffmpeg-generated test clip; no third-party music video frame appears in any
image.

Fonts are not bundled. The pages reference system font stacks only.
