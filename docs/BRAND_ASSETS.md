# Brand Assets

This repo keeps a minimal Meridian brand asset set under [`docs/assets/`](./assets/)
for repository presentation, social preview, release materials, and documentation.

## Included Assets

- `meridian_mark_flat.svg` — preferred flat mark for docs, UI, and light/dark backgrounds
- `meridian_wordmark_flat.svg` — flat wordmark for headers and supporting materials
- `meridian_lockup_flat.svg` — preferred combined mark + wordmark for README/repo presentation
- `logo_favicon_64.png` — legacy PNG fallback for small icon slots
- `logo_avatar_192.png` — legacy avatar for dark-background platforms
- `logo_banner_1200x630.jpg` — social preview / share image

## Why The README Now Uses The Lockup

The current raster mark is still not a good inline README image for GitHub's
default white background. The new flat SVG lockup exists specifically to solve
that problem without dragging the old leather/3D treatment into the OSS repo.

The README should use the flat lockup, not the legacy raster avatar/banner.

## Usage Guardrails

- Prefer the flat SVG assets for README, docs, and UI surfaces.
- Use the raster PNG/JPG assets only where an image fallback or social banner is needed.
- Do not stretch, recolor, or crop asymmetrically.
- Do not use the banner image inline as hero art in technical docs.
- Do not use the raster avatar on white backgrounds when the flat SVG mark is available.

## Future Improvement

The next brand step should be a fully production-tested wordmark and icon set
with explicit light/dark variants, plus export-ready PNGs derived from the SVG
master files instead of the old textured raster source.
