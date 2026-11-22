# mutant.kiwi Aerial Imagery Explorer

> **[https://imagery.mutant.kiwi/](https://imagery.mutant.kiwi/)**

A browser-based map viewer for exploring New Zealand's current, historical aerial and near-infrared photography. Click anywhere on the map to query all imagery series intersecting that location, inspect metadata, and stream Cloud-Optimised GeoTIFFs directly onto the map for visual comparison.

The viewer itself is a single static HTML file with no backend: the spatial query and the COG decoding both happen in the browser. One optional Lambda exists, purely to shorten project links — if it is unreachable the viewer falls back to a self-contained link and keeps working.

Also available as a QGIS PlugIn [https://github.com/MutantKiwi/aerial-image-viewer-qgis](https://github.com/MutantKiwi/aerial-image-viewer-qgis)

---

## Features

### Map & Navigation
- **Basemaps** — three current layers via the [LINZ Basemaps API](https://basemaps.linz.govt.nz/) and five scanned historic NZMS series from [mapspast.org.nz](https://mapspast.org.nz), grouped in the dropdown
- **Compass** — rotating compass top-right, click to reset north
- **NZTM coordinates** — live cursor position in NZTM2000 Easting/Northing (whole metres)
- **Place search** — geocoder for NZ place names

### Imagery Discovery
- **Point query** — click anywhere to find all imagery sheets covering that location across 712,857 sheets nationwide
- **Grouped results** — `REGION AERIAL IMAGERY` groups (alphabetical) with `NEW ZEALAND SATELLITE IMAGERY` always last
- **Sorted newest first** — within each group, results ordered by year descending
- **Near-infrared indicator** — NIR imagery highlighted with a pink-red badge in the results panel

### COG Streaming
- **Live rendering** — stream any COG tile directly into the browser viewport via HTTP Range requests
- **Multi-layer overlay** — stack multiple COG layers simultaneously; managed via a floating panel
- **Overview selection** — automatically picks the optimal overview level for the current zoom
- **Per-layer opacity slider** — adjust each layer's transparency independently
- **Layer visibility toggle** — show/hide individual layers or all layers at once
- **Memory-safe rendering** — uses `canvas.toBlob()` + `createObjectURL()`, revoking previous URLs on each re-render

### LINZ Basemaps WMTS

Where a collection has a matching published tile layer, the viewer can add it as a served pyramid instead of decoding the COG — faster, and it covers the whole survey rather than one sheet.

- **Add / Hide WMTS** — toggle the served tile layer for a collection, managed in the same sheets bar as COG overlays
- **Copy Tile URL** — the XYZ template, ready to paste into any client
- **QGIS layer file** — downloads a `.qlr` carrying the full EPSG:2193 `spatialrefsys` block, so it opens in the right place
- **ArcGIS Pro layer file** — downloads a `.lyrx` using `CIMProjectServerConnection` with `serverType: "WMTS"`, which is what makes Pro actually connect rather than just show stored metadata
- **Matching** — collections are keyed to Basemaps layer names through `basemaps_layers.json`, a 754-entry sidecar keyed on the collection path

Note that the viewer consumes the **WebMercatorQuad** tile matrix, because MapLibre reads Web Mercator tiling only. The `.qlr` and `.lyrx` exports point at **NZTM2000Quad**, which is what desktop GIS should use.

### Sharing

- **Save Search** — a link to a place and its result list
- **Save Project** — a link to everything on the map: basemap, every COG sheet and WMTS layer with its own opacity and visibility, and on the beta page the open Retrolens photo with its corner warp
- **Short links** — the project payload is deflated, then parked in the bucket by a Lambda so the link carries only an 8-character id. A 50-sheet project is about 60 characters. If the shortener is unreachable the whole project travels in the hash instead, which is longer but never rots

### Near-Infrared (NIR) Imagery
- **CIR false-colour** — NIR imagery automatically rendered as Colour Infrared composite: NIR→Red, Red→Green, Green→Blue. Healthy vegetation appears bright red, water very dark
- **Auto-detection** — triggered by "near-infrared" in the layer title, no manual configuration
- **Full 5-band decode** — R, G, B, NIR, Alpha with correct ZSTD+PREDICTOR=2+INTERLEAVE=PIXEL handling

### Performance
- **Debounced re-render** — 150ms debounce on `moveend` prevents thrashing during pan/zoom
- **Overview cache** — overview headers fetched once per COG and cached for all subsequent renders
- **System fonts** — no external font CDN blocking page load

---

## Live Demo

**[https://imagery.mutant.kiwi/](https://imagery.mutant.kiwi/)**

Covers all of New Zealand — 712,857 imagery sheets from 1940 to 2026 including:

- Historical aerial photography (1940s–1990s)
- Modern high-resolution rural and urban aerial surveys (0.075m–0.5m)
- Near-infrared aerial photography (4-band + alpha)
- NZ-wide 10m satellite imagery (2020–2025)

---

## Architecture

A **single self-contained HTML file** — no build step. All map logic runs client-side.

```
Browser
  │
  ├── MapLibre GL JS           # WebGL map rendering
  │     ├── LINZ Basemaps      # Topo Lite / Topo Gridless / Aerial
  │     ├── mapspast.org.nz    # 5 scanned NZMS series (Web Mercator tiles)
  │     └── Basemaps WMTS      # per-collection served pyramids (XYZ)
  │
  ├── FlatGeobuf               # Spatial query
  │     └── all_imagery.fgb    # 712,857 features, Hilbert R-tree, EPSG:2193
  │
  ├── GeoTIFF.js               # COG tile fetching via HTTP Range requests
  │     ├── WEBP               # Native (geotiff.js + browser)
  │     ├── ZSTD               # fzstd — near-infrared imagery
  │     └── LERC               # LercDecode.js (self-hosted fallback)
  │
  ├── basemaps_layers.json     # collection path -> Basemaps layer name (754)
  │
  └── proj4.js                 # WGS84 ↔ EPSG:2193 (NZTM2000)

Lambda (optional, writes only)
  └── project-link             # POST payload -> p/<id>.json, returns the id
                               # reads come from CloudFront, same-origin
```

### Repository layout

| Path | What it is |
|---|---|
| `index.html` | The whole viewer |
| `lambda/project-link/handler.py` | The project-link shortener |
| `README.md` | This file |

Branches: `main` is what serves imagery.mutant.kiwi; `retrolens` adds the Retrolens survey photos and is published as `beta.html`; `next` holds unmerged multi-dataset work. `basemaps-wmts` was merged into `main` and `retrolens` on 2026-11-21.

### COG Rendering Pipeline

1. `GeoTIFF.fromUrl()` opens the COG, reads image count and bounding box
2. Map viewport projected into NZTM2000
3. Viewport/COG intersection computes the visible pixel window
4. Best overview level selected (cached after first render)
5. `readRasters()` fetches only visible tiles via HTTP Range requests
6. Compression detected via magic-byte probe → routed to correct decoder
7. NIR imagery remapped to CIR false-colour (NIR→R, Red→G, Green→B)
8. Bands normalised → canvas → `toBlob()` → `createObjectURL()`
9. MapLibre `image` source added/updated; previous Blob URL revoked

---

## Basemaps

Switched via dropdown below the search bar, in two groups.

| Option | Type | Source | Notes |
|---|---|---|---|
| **NZ Topo Lite** *(default)* | Vector | LINZ Basemaps | Clean topographic style, fast |
| NZ Topo Gridless | Raster | LINZ Basemaps | Scanned topo map tiles |
| NZ Aerial Imagery | Raster | LINZ Basemaps | LINZ national aerial mosaic |
| NZMS 260 (1999) | Raster | mapspast.org.nz | Scanned historic series, z1–15 |
| NZMS 260 / NZMS 1 (1989) | Raster | mapspast.org.nz | " |
| NZMS 1 (1979) | Raster | mapspast.org.nz | " |
| NZMS 1 (1969) | Raster | mapspast.org.nz | " |
| NZMS 1 (1959) | Raster | mapspast.org.nz | " |

The mapspast tiles come from the Catalyst Cloud object-storage endpoint rather than the `au.mapspast.org.nz` alias, which answers on http only — this page is https, so those tiles would be blocked as mixed content and silently never appear. The same bucket also holds an EPSG:2193 pyramid, which MapLibre cannot use.

Overlays survive basemap switches: they are snapshotted and re-added after the new style loads. A COG is rebuilt as an image source and refilled on the next render; a WMTS layer is rebuilt as the raster tile source it actually is, since nothing refills it.

---

## Data

Served via **CloudFront** at `imagery.mutant.kiwi`, backed by an S3 bucket with CloudFront-only access policy (Block Public Access enabled).

| File | Purpose |
|---|---|
| `all_imagery.fgb` | Master FlatGeobuf — 712,857 footprints, Hilbert R-tree spatial index, EPSG:2193 (510.7 MB) |
| `basemaps_layers.json` | Collection path → LINZ Basemaps layer name, 754 entries |
| `p/<id>.json` | Saved projects, content-addressed and immutable |
| `LercDecode.js` | Self-hosted LERC decoder |

FGB feature properties: `title`, `region`, `year`, `asset_id` (the tile ID, e.g. `CI06_5000_0205`), `asset_url_image` (COG URL), `title_unicode` (series slug), `collection_url`, polygon geometry in EPSG:2193.

The harvester can also stamp a `basemaps_name` field onto each feature, which would make the sidecar unnecessary. That change is committed but not yet deployed into the build zip, so the published index does not carry the field and the viewer falls back to matching on `collection_url`.

---

## Libraries

| Library | Version | Purpose |
|---|---|---|
| [MapLibre GL JS](https://maplibre.org/) | 4.5.0 | WebGL map rendering |
| [FlatGeobuf](https://flatgeobuf.org/) | 3.35.0 | Streaming spatial queries |
| [GeoTIFF.js](https://geotiffjs.github.io/) | 2.1.3 | COG parsing, tile fetching, WEBP decode |
| [fzstd](https://github.com/101arrowz/fzstd) | 0.1.1 | ZSTD decompression (NIR imagery) |
| [LercDecode.js](https://github.com/Esri/lerc) | 3.x | LERC decompression (self-hosted) |
| [proj4js](https://proj4js.org/) | 2.9.0 | CRS reprojection (WGS84 ↔ NZTM2000) |
| [Sentry SDK](https://sentry.io/) | 7.99.0 | Error tracking via Bugsink |
| [LINZ Basemaps](https://basemaps.linz.govt.nz/) | — | NZ topographic and aerial base layers |

---

## Browser Requirements

| Feature | Minimum |
|---|---|
| WebGL | Chrome 56+, Firefox 51+, Safari 15+ |
| HTTP Range requests | All modern browsers |
| WebP decode | Chrome 32+, Firefox 65+, Safari 14+ |
| `createImageBitmap` | Chrome 50+, Firefox 42+, Safari 15+ |

---

## Development

No build step. Edit `index.html` directly.

```bash
# Deploy, if you can reach S3 from where you are
aws s3 cp index.html s3://gbf.nz.imagery/index.html \
  --content-type "text/html; charset=utf-8" --cache-control "max-age=300"
aws cloudfront create-invalidation --distribution-id E5CXYG7GQUQ4N \
  --paths "/index.html"
```

### Deploying from GitHub

Where S3 is not directly reachable, CodeBuild can pull from this repo instead. It clones the public repo, stages to a prefix the build role is allowed to write, and a server-side copy promotes it — so the bytes are never re-uploaded and the checksum can be verified end to end.

```bash
aws codebuild start-build --project-name linz-delta-report \
  --source-type-override NO_SOURCE \
  --buildspec-override file://deploy-buildspec.yml
```

The buildspec clones `main` and `retrolens`, prints `md5sum` for both, and copies them to `staging/deploy-index.html` and `staging/deploy-beta.html`. Promote by comparing those checksums against the local files, then `CopyObject` to the bucket root.

### The project-link Lambda

```bash
cd lambda/project-link && zip -X project-link.zip handler.py
aws lambda update-function-code --function-name project-link \
  --zip-file fileb://project-link.zip --region ap-southeast-2
```

| Setting | Value |
|---|---|
| Runtime | python3.12, arm64, 128 MB, 10 s |
| Reserved concurrency | 2 — a hard ceiling on spend |
| Body cap | 4 KB (`MAX_BODY`) |
| IAM | `s3:PutObject` / `s3:GetObject` on `gbf.nz.imagery/p/*` only |
| Alarm | `project-link-unusual-volume` → SNS `linz-delta-report-alerts` at >500 invocations/hour |

The debug panel (accessible via the map UI) logs FGB queries, COG render events, compression routing, overview selection, and errors in real time.

---

## Acknowledgements

- Imagery: [Land Information New Zealand (LINZ)](https://www.linz.govt.nz/) — [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- Basemaps: [LINZ Basemaps](https://basemaps.linz.govt.nz/) — © Toitū Te Whenua Land Information New Zealand
- Map rendering: [MapLibre GL JS](https://maplibre.org/)
