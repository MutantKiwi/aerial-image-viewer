# mutant.kiwi Aerial Imagery Explorer

A browser-based map viewer for exploring New Zealand historical aerial photography. Click anywhere on the map to query intersecting imagery layers, inspect metadata, and stream Cloud Optimised GeoTIFFs directly onto the map for visual comparison.

---

## Features

- **Point-query imagery** — click the map to find all aerial photo series covering that location
- **COG streaming** — load GeoTIFF tiles directly in the browser, rendered at viewport resolution
- **Multi-COG overlay** — stack multiple imagery layers simultaneously for comparison
- **Layer extents** — toggle footprint polygons showing the spatial coverage of each dataset
- **Multi-compression support** — handles WEBP, LERC, LERC+Zstd, and ZSTD+Predictor COGs transparently
- **Metadata cards** — expandable result cards showing title, region, year, asset ID and more
- **Error tracking** — integrated Bugsink (Sentry-compatible) for production diagnostics
- **Debug panel** — real-time diagnostic window showing render events, errors, and layer activity

---

## Architecture

### Overview

The application is a single self-contained HTML file with no build step. All logic runs client-side — there is no backend server. Data is fetched on demand directly from S3.

```
Browser
  │
  ├── MapLibre GL JS          # Base map rendering (OpenFreeMap dark style)
  │
  ├── FlatGeobuf (FGB)        # Spatial index + feature metadata
  │     └── S3 bucket         # .fgb files per imagery series
  │
  ├── GeoTIFF.js + Pool       # COG tile fetching via HTTP Range requests
  │     ├── Browser WebP      # WEBP tile decompression (native, via Pool workers)
  │     ├── @esri/lerc        # LERC / LERC+Zstd tile decompression (on demand)
  │     └── ZstdCodec/fzstd   # ZSTD tile decompression (on demand)
  │
  └── proj4.js                # CRS reprojection (WGS84 ↔ EPSG:2193 NZTM2000)
```

### Coordinate Systems

All FGB files are stored in **EPSG:2193 (NZTM2000)** — New Zealand Transverse Mercator in metres. Map clicks arrive as **WGS84 (EPSG:4326)**. `proj4.js` handles bidirectional conversion at query time and during COG viewport calculations.

### Query Flow

1. User clicks the map → click coordinates converted from WGS84 → NZTM2000
2. Each configured FGB layer is queried with a bounding-box rectangle
3. Returned features are tested for point-in-polygon against the click point
4. Matching features are rendered as result cards in the side panel
5. Footprint geometry is drawn on the map as a highlight layer

### COG Rendering

1. `GeoTIFF.fromUrl()` opens the COG with `allowFullFile: true`
2. The current map viewport is projected into the COG's native CRS (NZTM2000)
3. The viewport/COG intersection is computed to determine the visible window
4. `readRasters({ pool })` fetches only the visible tile data via HTTP Range requests
5. Compression is handled automatically (see table below)
6. Raw raster bands are normalised to 0–255 and written to a canvas
7. The canvas is added as a `raster` source in MapLibre via `addSource` / `updateImage`
8. On `moveend` all active COGs re-render at the new viewport resolution

### Compression Handling

NZ imagery COGs use a variety of compression methods. The app detects the compression tag from the TIFF file directory and routes to the appropriate decoder:

| TIFF Tag | Compression | Handler |
|----------|-------------|---------|
| 50002 | WEBP (lossless) | `GeoTIFF.Pool` — browser-native WebP in worker threads |
| 5, 8 | LZW / Deflate | `GeoTIFF.Pool` — geotiff.js native |
| 50000 | LERC | Tile-fetch fallback + `@esri/lerc` |
| 50001 | LERC + Zstd | Tile-fetch fallback + `@esri/lerc` (includes Zstd internally) |
| 50003 | ZSTD + Predictor=2 | Tile-fetch fallback + `ZstdCodec`/`fzstd` + horizontal differencing undo |

The primary path (`readRasters` + Pool) is attempted first. If it fails, the compression tag is inspected and the appropriate fallback is invoked. Fallback decoders fetch raw tile bytes directly via HTTP Range requests, decompress them, and reassemble the raster manually.

`@esri/lerc` and the Zstd library are loaded asynchronously in the background on page load (ESRI CDN → jsdelivr → unpkg). The debug panel reports their status on startup.

---

## Data Sources

All spatial data is served from an **AWS S3** bucket (`s3://gbf.nz.imagery`).

| File type | Purpose |
|-----------|---------|
| `.fgb` (FlatGeobuf) | Spatial index of image footprints + metadata per series |
| `.tif` (COG) | Cloud Optimised GeoTIFF imagery tiles |

FGB files contain feature properties including `title`, `region`, `year`, `assest_id` (note: source data contains this typo), `asset_url_image` (COG URL), and polygon geometry in NZTM2000.

---

## Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| [MapLibre GL JS](https://maplibre.org/) | 4.5.0 | Interactive WebGL map |
| [FlatGeobuf](https://flatgeobuf.org/) | 3.35.0 | Streaming spatial file format |
| [GeoTIFF.js](https://geotiffjs.github.io/) | 2.1.3 | COG tile fetching, decoding, and worker pool |
| [@esri/lerc](https://github.com/Esri/lerc) | 4.0.1 | LERC and LERC+Zstd decompression (on demand) |
| [zstd-codec](https://github.com/yoshihitofujiwara/zstd-codec) | 0.1.5 | ZSTD decompression for geotiff.js 2.1.x (on demand) |
| [fzstd](https://github.com/101arrowz/fzstd) | 0.1.1 | ZSTD decompression fallback for geotiff.js 2.2+ (on demand) |
| [proj4js](https://proj4js.org/) | 2.9.0 | CRS reprojection (WGS84 ↔ NZTM2000) |
| [Sentry SDK](https://sentry.io/) | 7.99.0 | Error tracking (via Bugsink) |
| [OpenFreeMap](https://openfreemap.org/) | — | Base map tiles (dark style) |

`@esri/lerc`, `zstd-codec`, and `fzstd` are loaded on demand via CDN and do not block initial page load.

---

## Configuration

Imagery layers are configured in the `CONFIG.layers` array at the top of the script:

```javascript
{
  url:           'https://s3.../layer_name.fgb',  // FlatGeobuf index
  label:         'Northland 0.1m (2014–2015)',     // Display name
  imageUrlField: 'asset_url_image'                 // FGB property containing COG URL
}
```

Adding a new series requires only uploading an FGB file and adding one entry to this array. Compression type is detected automatically — no per-layer configuration needed.

---

## Error Tracking

Errors are reported to a self-hosted [Bugsink](https://www.bugsink.com/) instance using the Sentry SDK:

```javascript
Sentry.init({
  dsn: "https://...@mutantkiwi.bugsink.com/1",
  tracesSampleRate: 0.2
});
```

Errors logged via `debugErr()` in the diagnostic panel are also forwarded to Bugsink as captured messages. MapLibre sprite/image warnings are suppressed via `beforeSend`.

---

## Browser Requirements

| Feature | Minimum |
|---------|---------|
| WebGL | Chrome 56+, Firefox 51+ |
| HTTP Range requests | All modern browsers |
| WebP image decoding | Chrome 32+, Firefox 65+, Safari 14+ |
| Web Workers (GeoTIFF Pool) | All modern browsers |

---

## Development

No build step required. Edit `index.html` directly and open in a browser.

The built-in debug panel (bottom-right, red border) logs all layer queries, COG render events, compression fallback activity, and library load status in real time.
