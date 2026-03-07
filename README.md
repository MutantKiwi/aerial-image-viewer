# mutant.kiwi Aerial Imagery Explorer

A browser-based map viewer for exploring New Zealand historical aerial photography. Click anywhere on the map to query intersecting imagery layers, inspect metadata, and stream Cloud Optimised GeoTIFFs directly onto the map for visual comparison.

---

## Features

- **Point-query imagery** — click the map to find all aerial photo series covering that location
- **COG streaming** — load GeoTIFF tiles directly in the browser, rendered at viewport resolution
- **Multi-COG overlay** — stack multiple imagery layers simultaneously for comparison
- **Layer extents** — toggle footprint polygons showing the spatial coverage of each dataset
- **LERC + Zstd decompression** — handles modern COG compression formats via `@esri/lerc`
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
  ├── GeoTIFF.js              # COG tile fetching via HTTP Range requests
  │     └── @esri/lerc        # LERC / LERC+Zstd tile decompression
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
4. `readRasters()` fetches only the visible tile data via HTTP Range requests
5. Raw raster bands are normalised to 0–255 and written to a canvas
6. The canvas is added as a `raster` source in MapLibre using `addSource` / `updateImage`
7. On `moveend` all active COGs re-render at the new viewport resolution

### LERC Decompression

COGs from the NZ imagery archive use **LERC compression (method 50000)** and **LERC+Zstd (method 50001)**. `geotiff.js` does not natively support these. A fallback path:

1. Detects the compression error from `geotiff.js`
2. Reads tile offsets and byte counts directly from the TIFF file directory
3. Fetches each tile individually via HTTP Range requests
4. Decodes using `@esri/lerc` (which bundles its own Zstd decompressor)
5. Assembles tiles into a full raster and resamples to the output viewport size
6. Falls back through overview levels (smallest first) to minimise data transfer

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
| [GeoTIFF.js](https://geotiffjs.github.io/) | 2.1.3 | COG tile fetching and decoding |
| [@esri/lerc](https://github.com/Esri/lerc) | 4.0.1 | LERC and LERC+Zstd decompression |
| [proj4js](https://proj4js.org/) | 2.9.0 | CRS reprojection |
| [Sentry SDK](https://sentry.io/) | 7.99.0 | Error tracking (via Bugsink) |
| [OpenFreeMap](https://openfreemap.org/) | — | Base map tiles (dark style) |

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

Adding a new series requires only uploading an FGB file and adding one entry to this array.

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
| `@esri/lerc` WASM | Chrome 57+, Firefox 52+ |

---

## Development

No build step required. Edit `index.html` directly and open in a browser.

The built-in debug panel (bottom-right, red border) logs all layer queries, COG render events, compression fallback activity, and errors in real time.
