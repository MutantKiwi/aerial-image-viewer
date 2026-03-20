# NZ Imagery COG — Compression & TIFF Tag Issues

## Summary

New Zealand aerial and near-infrared imagery hosted on the LINZ S3 bucket (`nz-imagery`) is served as Cloud-Optimised GeoTIFFs (COGs). During development of the Mutant Kiwi Aerial Imagery Explorer, three distinct compression problems were encountered that required custom decoding logic. The core issue is that **the TIFF compression tag cannot be trusted** — files frequently declare one compression method while the actual tile data uses a completely different format. A tile-level magic-byte probe is required before routing to the correct decoder.

---

## 1. Standard Aerial Imagery — WEBP with Misleading LERC Tag

### What gdalinfo reports
```
COMPRESSION=WEBP
```

### What geotiff.js sees
The TIFF `Compression` tag in the Image File Directory (IFD) reports `50001` (LERC+Zstd), but the actual tile bytes begin with `52 49 46 46` — the RIFF magic header used by WEBP.

### Why this happens
GDAL's COG driver and the LINZ basemaps pipeline appear to write an incorrect compression tag in some output files, or the tag reflects an intermediate processing step rather than the final tile encoding. The GDAL "ghost header" (a hidden metadata block at the start of some COGs) may also carry conflicting information.

### Impact
geotiff.js 2.1.3 handles WEBP natively via its worker Pool. If the code blindly routes tag `50001` to a LERC decoder, it either fails silently or produces garbage data. The Pool itself can also crash with `undefined.offset` errors from `blockedsource.js` on certain tile configurations, requiring a single-threaded fallback.

### Fix
Fetch the first 4 bytes of the first tile via HTTP Range request before routing. If magic bytes are `52 49 46 46` (RIFF/WEBP), bypass the LERC path entirely and use `image.readRasters()` directly.

---

## 2. Near-Infrared Imagery — ZSTD with LERC Tag

### What gdalinfo reports
```
COMPRESSION=ZSTD
INTERLEAVE=PIXEL
PREDICTOR=2
```
With 5 bands: Red (1), Green (2), Blue (3), NIR (4), Alpha (5) — all Byte/Uint8.

### What geotiff.js sees
The TIFF `Compression` tag again reports `50000` (LERC), but tile bytes begin with `28 B5 2F FD` — the Zstandard magic number.

### Why this happens
The same mislabelling pattern as standard imagery, but here the actual compression is ZSTD rather than WEBP. The LINZ pipeline appears to use tag `50000` as a generic "non-standard" marker regardless of actual encoding.

### Complications

#### PREDICTOR=2 (Horizontal Differencing)
With ZSTD compression, GDAL applies a horizontal differencing predictor before compressing. Each sample value is stored as a delta from the previous sample of the same band in the same row, not an absolute value. This must be reversed after decompression.

With `INTERLEAVE=PIXEL` and 5 bands, samples are laid out in memory as:
```
R0 G0 B0 NIR0 A0  R1 G1 B1 NIR1 A1  R2 G2 B2 NIR2 A2 ...
```
The step between same-band samples across pixels is `nBands × bytesPerSample` (5 bytes for 5×Uint8), **not 1 byte**. An earlier implementation used a step of 1 byte which caused every sample to be contaminated by the adjacent band's delta, producing entirely wrong values.

#### BitsPerSample field format
geotiff.js returns `BitsPerSample` as a plain JavaScript object with numeric keys (`{0:8, 1:8, 2:8, 3:8, 4:8}`) rather than a real Array when there are multiple bands. This means:

- `Array.isArray(fd.BitsPerSample)` returns `false`
- `fd.BitsPerSample[0]` returns `8` (works by accident)
- Using the raw object in arithmetic (e.g. `bitsPerSample / 8`) produces `NaN`

The value must be extracted with `Object.values(bpsRaw)[0]`. When `bytesPerSample` becomes `NaN`, the band typed array falls through to `Float32Array` (the default), and the expected tile byte length becomes `NaN`, breaking all size calculations.

#### Band typed arrays
Pixel bands must be stored in `Uint8Array` for 8-bit data, not `Float32Array`. Assigning a raw byte value like `147` into a `Float32Array` slot stores the integer bit pattern reinterpreted as a 32-bit IEEE float, producing values like `-9.633e-22` or `-81,951,809,536`. This was the root cause of all-black rendering — `toRGBA()` received values that `normalise()` (which clamps to 0-255) would correctly zero out.

### Fix
1. Parse `BitsPerSample` using `Object.values()` to handle the object-keyed format
2. Allocate band arrays as `Uint8Array` / `Uint16Array` / `Float32Array` based on actual bit depth
3. Undo PREDICTOR=2 using step = `nBands × bytesPerSample`, not `bytesPerSample`

---

## 3. Band Display — CIR False-Colour Composite

Near-infrared COGs have 5 bands in order: Red (1), Green (2), Blue (3), NIR (4), Alpha (5).

Displaying bands 1–3 as RGB produces a normal-looking aerial photo with no NIR content visible. The standard visualisation for NIR imagery is **Colour Infrared (CIR)**:

| Display channel | Source band | Rationale |
|---|---|---|
| Red | Band 4 — NIR | NIR reflectance drives the red channel |
| Green | Band 1 — Red | Red shifted to green for contrast |
| Blue | Band 2 — Green | Green shifted to blue |
| Alpha | Band 5 — Alpha | Transparency mask |

This makes healthy vegetation appear bright red (high NIR reflectance), water very dark (low NIR absorption), and urban/bare ground grey-brown — the conventional false-colour standard in remote sensing and the default view on LINZ Basemaps when the NIR layer is active.

Detection uses the layer title containing "near-infrared" (case-insensitive), consistent with the pink-red card badge already applied in the results panel.

---

## 4. Compression Routing Logic

The final routing implemented in `readRastersWithFallback()`:

```
Tag 50000 or 50001 (nominally LERC or LERC+Zstd)
  → Probe first 4 bytes of first tile via HTTP Range
    → 52 49 46 46 (RIFF/WEBP)  → Standard readRasters()
    → 28 B5 2F FD (ZSTD magic) → readRastersZstd()
    → Other / probe fails       → readRastersLerc()

Tag 50003 (explicit ZSTD)
  → readRastersZstd()

All other tags (LZW=5, JPEG=6/7, Deflate=8/32946, direct WEBP=34892, None=1)
  → image.readRasters() — geotiff.js native decoder
    → Single-thread first (reliable)
    → Pool fallback if single-thread fails
```

The probe costs one 4-byte HTTP Range request per COG open. It is not repeated per tile or per viewport re-render.

---

## 5. geotiff.js Worker Pool Issues

The Pool (`new GeoTIFF.Pool()`) spawns web workers for parallel tile decoding and is intended to speed up CPU-bound decompression. In practice it fails with `Cannot read properties of undefined (reading 'offset')` from inside `blockedsource.js` on certain NZ imagery tile configurations. The failure is non-deterministic and appears related to tile boundary or overlap edge cases in the blocked HTTP source implementation.

**Fix:** Single-threaded `readRasters()` is tried first. Pool is only used as a fallback if single-thread fails. For ZSTD and LERC paths, the Pool is never used — tile fetching and decoding is handled entirely via manual HTTP Range requests.

---

## 6. Libraries

| Library | Purpose | Source |
|---|---|---|
| geotiff.js 2.1.3 | COG header parsing, HTTP range tile fetching, WEBP/LZW/Deflate/JPEG decode | jsDelivr CDN |
| fzstd 0.1.1 | ZSTD decompression for near-infrared tiles | jsDelivr CDN |
| LercDecode.js | LERC decompression for any genuine LERC tiles | Self-hosted at imagery.mutant.kiwi |

---

*Last updated: March 2026 — based on NZ imagery served from `nz-imagery.s3-ap-southeast-2.amazonaws.com`*
