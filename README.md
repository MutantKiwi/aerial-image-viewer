# mutant.kiwi Aerial Imagery Explorer

> **[https://imagery.mutant.kiwi/](https://imagery.mutant.kiwi/)**

A browser-based map viewer for exploring New Zealand's historical aerial and near-infrared photography. Click anywhere on the map to query all imagery series intersecting that location, inspect metadata, and stream Cloud-Optimised GeoTIFFs directly onto the map for visual comparison — all client-side, no backend required.

Also available as a QGIS PlugIn [https://github.com/MutantKiwi/aerial-image-viewer-qgis](https://github.com/MutantKiwi/aerial-image-viewer-qgis)

---

## Features

### Map & Navigation
- **LINZ basemaps** — switchable base layers: NZ Topo Lite *(default)*, NZ Topo Gridless, and NZ Aerial Imagery, all via the [LINZ Basemaps API](https://basemaps.linz.govt.nz/)
- **Compass** — rotating compass top-right, click to reset north
- **NZTM coordinates** — live cursor position in NZTM2000 Easting/Northing (whole metres)
- **Place search** — geocoder for NZ place names

### Imagery Discovery
- **Point query** — click anywhere to find all imagery sheets covering that location across 621,728 sheets nationwide
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

Covers all of New Zealand — 621,728 imagery sheets from 1940 to 2025 including:

- Historical aerial photography (1940s–1990s)
- Modern high-resolution rural and urban aerial surveys (0.075m–0.5m)
- Near-infrared aerial photography (4-band + alpha)
- NZ-wide 10m satellite imagery (2020–2025)

---

## Architecture

A **single self-contained HTML file** — no build step, no backend. All logic runs client-side.

```
Browser
  │
  ├── MapLibre GL JS           # WebGL map rendering
  │     └── LINZ Basemaps      # Topo Lite / Topo Gridless / Aerial
  │
  ├── FlatGeobuf               # Spatial query
  │     └── all_imagery.fgb    # 621,728 features, Hilbert R-tree, EPSG:2193
  │
  ├── GeoTIFF.js               # COG tile fetching via HTTP Range requests
  │     ├── WEBP               # Native (geotiff.js + browser)
  │     ├── ZSTD               # fzstd — near-infrared imagery
  │     └── LERC               # LercDecode.js (self-hosted fallback)
  │
  └── proj4.js                 # WGS84 ↔ EPSG:2193 (NZTM2000)
```

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

## Compression Handling

NZ imagery TIFF compression tags **frequently misreport the actual tile encoding**. A 4-byte magic-number probe of the first tile is performed before routing.

| TIFF Tag | Declared | Actual | Decoder |
|---|---|---|---|
| 50001 | LERC+Zstd | **WEBP** (`52 49 46 46`) | `readRasters()` native |
| 50000 | LERC | **ZSTD** (`28 B5 2F FD`) | `readRastersZstd()` + fzstd |
| 50000 | LERC | LERC | `readRastersLerc()` + LercDecode.js |
| 50003 | ZSTD | ZSTD | `readRastersZstd()` + fzstd |
| 5, 8, 34892 | LZW/Deflate/WEBP | As declared | `readRasters()` native |

**NIR ZSTD specifics:** `INTERLEAVE=PIXEL` + `PREDICTOR=2` — undo step must be `nBands × bytesPerSample`. `BitsPerSample` is returned by geotiff.js as a plain object `{0:8, 1:8, ...}` requiring `Object.values()` to parse. Band arrays must be `Uint8Array` for 8-bit data, not `Float32Array`.

See [`COMPRESSION-TIFF-TAG-ISSUES.md`](https://github.com/MutantKiwi/aerial-image-viewer/blob/main/COMPRESSION-TIFF-TAG-ISSUES.md) for full technical detail.

---

## Basemaps

Switched via dropdown below the search bar. All served by the [LINZ Basemaps API](https://basemaps.linz.govt.nz/).

| Option | Type | Notes |
|---|---|---|
| **NZ Topo Lite** *(default)* | Vector | Clean topographic style, fast |
| NZ Topo Gridless | Raster | Scanned topo map tiles |
| NZ Aerial Imagery | Raster | LINZ national aerial mosaic |

COG overlay layers survive basemap switches — snapshotted and re-added after the new style loads.

---

## Data

Served via **CloudFront** at `imagery.mutant.kiwi`, backed by an S3 bucket with CloudFront-only access policy (Block Public Access enabled).

| File | Purpose |
|---|---|
| `all_imagery.fgb` | Master FlatGeobuf — 621,728 footprints, Hilbert R-tree spatial index, EPSG:2193 |
| `LercDecode.js` | Self-hosted LERC decoder |

FGB feature properties: `title`, `region`, `year`, `asset_id`, `asset_url_image` (COG URL), `title_unicode` (series slug), polygon geometry in EPSG:2193.

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
# Deploy
aws s3 cp index.html s3://your-bucket/index.html
aws cloudfront create-invalidation --distribution-id YOUR_ID --paths "/*"
```

The debug panel (accessible via the map UI) logs FGB queries, COG render events, compression routing, overview selection, and errors in real time.

---

## Acknowledgements

- Imagery: [Land Information New Zealand (LINZ)](https://www.linz.govt.nz/) — [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- Basemaps: [LINZ Basemaps](https://basemaps.linz.govt.nz/) — © Toitū Te Whenua Land Information New Zealand
- Map rendering: [MapLibre GL JS](https://maplibre.org/)
