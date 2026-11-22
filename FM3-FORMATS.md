# FM3 asset formats: what we know and where it comes from

Working notes for loading Forza Motorsport 3's own files (renderer project, M1 stage 2+). Big-endian throughout.
"Verified" = checked against FM3 files and captured frames here; "FM4/FH1" = from community work on the same engine,
not yet checked on FM3.

## Sources researched (2026-11-22)

| Source | Covers | Use for FM3 |
|---|---|---|
| [D3FEKT/ForzaTechStudio](https://github.com/D3FEKT/ForzaTechStudio) | FH2-6, FM5-2023 (Xbox One / PC): `.modelbin`, `.swatchbin`, newer `.carbin`, `.minizip` | Little: later-gen formats. Confirms zip method 21 = LZX. Vertex packing hints (u16 UV pairs, s16 normals, 10:10:10:2 tangents) |
| [Nenkai/ForzaTools](https://github.com/Nenkai/ForzaTools), [Nenkai/010GameTemplates](https://github.com/Nenkai/010GameTemplates/tree/main/Forza) | FH4/FM5+ bundles, textures (XG tiling = Xbox One) | Little; `CarScene_carbin.bt` unread |
| [Doliman100/ForzaTech-extraction-tools](https://github.com/Doliman100/ForzaTech-extraction-tools) | FM5+ patterns (little-endian, u16 roots) | Not 360 |
| [FH1-ReImagined/ForzaHorizon1-ReImagined](https://github.com/FH1-ReImagined/ForzaHorizon1-ReImagined) | Forza Horizon 1 recomp on the FM4 engine: carbin, FM4 tracks (rmb command lists, PVS placements, collision), texture packs | **Most useful**: `docs/modding/carbin-format.md`, `docs/modding/fm4-cars.md`, `docs/festival_track_spike.md`, `docs/fm4-tracks.md`, `tools/fm4_pvs.py`, `tools/fm4_carbin.py`, `tools/rmb_lists.py`, `tools/fm4_col.py` |
| [FMdangaina/ForzaStudio-EVO](https://github.com/FMdangaina/ForzaStudio-EVO) (GPL-3.0, C#; after Mike Davis' Forza Studio 4.6) | **FM3 and FM4**: car `.carbin` (OBJ/FBX/glTF), `.xds` textures with Xenos untiling, FM3/FM4 track bins (`ForzaTrackBin.cs`, `ForzaTrackSection.cs`, `ForzaTrackSubSection.cs`, `ForzaVertex.cs`, `XdsTexture.cs`, `XenosTiling.cs`) | **Directly**: track mesh and vertex layout, UV transform, xds header, untiling. Not covered: `.pvs`, `.bix`, `.stx.bin` |
| [Coupe5E/Forza3EU-Recomp](https://github.com/Coupe5E/Forza3EU-Recomp) | Another FM3 recomp | Not read |

For FM3 specifically, ForzaStudio-EVO is the one source with format code; nothing public covers `.pvs`, `.bix` or `.stx.bin`
(searched: GitHub repos, Nenkai's templates, Doliman100, hl360-forza3, FM4CarModelTools; archived Xentax threads and
web search were not reachable).

## Archives

- **Verified:** zip members use method 21 = Xbox LZX (`tools/fm3unzip`, the FM3 recomp's `src/lzx.cpp`).

## Cars (`.carbin`)

- **Verified (FM3):** material records `u32 2, u32 len, name, u32 1` before each mesh's data; index lists (u16, 0xFFFF restart) and
  vertex buffers are uploaded unchanged, so captured draws are found verbatim (`tools/fm3_assets.py`).
- **Verified (FM3), the whole car** (`tools/fm3_car.py`): part sections (body, trunk, hooda, bumperRa..f, skirtLa..,
  glassLM, wingrace, ...): a header u32 2, u32 0, u32 0, u32 2, f32[3] car-space offset, f32[3] bbox min, f32[3] bbox
  max somewhere before the name (for glass panes thousands of bytes before, after their damage data), u32 name length,
  name, u32 2, u32 vertex count, u32 stride (40), vertices, subsections (u32 2, material name, u32 LOD, u32 index type,
  u32 material index, ..., UV offset/tile, u32 3, count, size, indices). Vertex: half4 position (car space = xyz * w +
  part offset; the vertex shader's `mad r4 = r1.xyz * r1.w + c190`), half2 UV0 at byte 8, packed normal/tangent and
  damage data after. Variants per part group (letters a-g, 'race'); the stock car uses one per group.
- **FH1/FM4:** strings are `u32 length + bytes`; `array<T>` = `u32 version(1), u32 count, T...`; root u32 (5 car, 3 wheel,
  1 part); CMesh = material/technique name, u32 LOD, u32 primitive (6 strip / 4 list), u32 material index, unpacking
  data, index buffer (FM4 v3: count, format 2/4); VertexBuffer v3 = version, count, stride, flags (bit 0 key follows,
  bit 1 data not in file), [key], data. FM4 car vertex, stride 32: 4 x s16 position (normalised, scaled by the
  unpacking data), 2 x u16 UV1, 2 x u16 UV2, 4 x s16 tangent-frame quaternion, 4 x s16 SH0 (baked light). Morphs:
  u32 FMT_10_11_11. Textures bound by sampler name (textures.xml), not stored in the carbin.

## Tracks

- **Verified (FM3, Ladera = folder `CrownJewel`):** `.rmb.bin` models hold, per mesh: name, u32 ?, vertex count, stride
  (16-40), vertices (f32[3] world-space position + packed attributes), material name, parameters, u32 prim (3 =
  strip), u32 index count, u32 index size, u16 indices (`tools/fm3_track.py`). Track pieces are world-space (identity
  header matrix); shared props (barriers, flags, plants) are in model space and placed elsewhere.
- **Verified (FM3), the full model file:** sections as ForzaStudio-EVO describes, and **each section's vertex block is
  shared by all its subsections** (one per material: u32 1, u32 2, name, u32 LOD, u32 index type, **u32 material index**,
  u32 1, u32 0 x4, f32 1.0 x4, f32[2] UV offset, f32[2] UV tile, u32 3, i32 index count, i32 index size, indices,
  u32 flag). After the last section, the **material table**: u32 x4, u32 count, then per material: u32 3, u32 shader
  index (into the file's `shaders\track\*.fx` list), u32 0, u32 1, u32 0, u32 1, u32 n + n vec4 parameters (the first
  is the colour: the pit lane's `Asphalt_Orange` is (0.655, 0.353, 0)), u32 1, u32 slot count + slots. Slots index the
  model's `.pvs` texture list (-1 none, -2 unused): **slot 0 = base texture, slot 7 = lightmap** (277 captured textures
  confirmed). 1,901 of Ladera's 1,914 files parse this way.
- **Vertex strides, extra:** stride 28 carries UV1 (the lightmap coordinate, decoded like UV0) at byte 24, in some
  sections at byte 20 (the one within 0..1); found by fitting captured lightmap UVs. Meshes without UV1 use UV0 for
  their lightmap. The sky dome (`<track>out.sky.rmb.bin`, stride 16) is position + u16 UV pair; FM3 centres it on the
  camera, lowered by TrackSettings.xml's `SkyboxHeightOffset` (Ladera -1150).
- **Shaders and their inputs (verified on the captured frame, `tools/fm3_shaders.py` + `fir_disasm.py --pixel`):** the
  pixel shader's constants **c0..cN are the material's parameter vectors** (material table), hardware texture slot k
  reads material slot k, slot 7 is the lightmap, c116 / c120-c123 hold each UV set's tile and offset, c247 / c248 the
  ambient / sun colours, c242 the fog colour. Recipes per family in [`tools/fm3_families.py`](tools/fm3_families.py)
  (terrain blend `lerp(t0 * tint, t1, mask.r)` with per-layer UV scales from the specular parameter vector; road
  `marks * grain(world x, z)`; paint; road edge; two-scale mix). Road-edge, mountain-road and shoulder-grass recipes
  are inferred from their textures (not in the captured frame).
- **Where UV0 sits** depends on shader and stride: byte 16 for most; byte 12 for `tree_*` cards (stride 24); byte 20 for
  the shoulder-grass `*_vclr_mix_3` (stride 28, byte 16 = vertex colour); terrain stride 28: UV0 16, second layer 20,
  mask/lightmap 24; terrain stride 32 with vertex colour (ARGB at 20): 16, 24, 28; road edges (stride 36): UV0 16,
  edge mask 20, lightmap 24. Stride 16 is position + UV (sky dome, the valley backdrop). Found by fitting captured UVs,
  and for meshes the frame did not show, by the one pair with the track-wide density of 0.143 UV per metre.
- **Textures without a `.bix`** (77 on Ladera, some full size, e.g. the grass tufts) are in the stx as `_0x<id>_s`
  entries. **Lightmap atlases** are only the DXT1 `_a` entries; the one DXT5 `_a` (0x28f) is something else, and atlas
  entries in its id range belong to the DXT1 atlas before it (the distant matte terrain).
- **`staticcarcubemap.xpr`** (per ribbon): XPR2 (`XPR2`, u32 header size 0x800, u32 data size, u32 count; entry
  `TXCM` "CarTrackCubemap"; D3D texture header with the fetch constant at 0x58; data from header size + 12): the static
  environment cube reflected by car paint and window glass, 256 x 256 DXT5 (endian 1, tiled), faces +X, -X, +Y, -Y, +Z,
  -Z every 64 KiB.
- Not geometry to draw as is: `flare_*` (the sun flare) and `LGHT_*` meshes (light volumes, no material).
- **ForzaStudio-EVO (matches our files: u32 version 4 = FM3, 6 = FM4; section count u32 at 0x74):** per section: u32 1;
  three float3 blocks each followed by f32 0; u32 1; name (i32 length + ASCII; text before the first `_` = type);
  u32 2; u32 vertex count; u32 stride; vertices; u32 1; u32 subsection count. Per subsection: u32 1, u32 2; name; u32 LOD;
  u32 index type (list / strip); u32 (0/1/2/5); u32 1; four u32 0; four f32 1.0; **f32[2] UV offset, f32[2] UV tile**;
  u32 3; i32 index count; i32 index size; u32 flag. UV = uv * tile + offset, then V = 1 - V. Strip restart -1.
  **Track vertex strides** (position f32[3]; normal = packed u32, 10:10:10 normalized; UVs = u16 pairs / 65535):
  12 pos; 16 +normal; 20 +UV0; 24 +UV0 +UV1; 28 +UV0 +8 bytes; 32 +UV0 +UV1 +8; 36 normal, 4 skipped, UV0, UV1, +8;
  40 +UV0 +UV1 +16 (skipped bytes undecoded: colour or lightmap data?).
- **FM4 (rmb_lists.py):** an `.fx` header with eight u32 words (area A/B/C sizes), 21 pass groups (12 opaque, 13
  transparent, 11/14/17 decals, 0 depth pre-pass), area A = 0xC8-byte list headers + patch table + marker
  `11223344 55667789`, area B = PM4 command buffers, area C = fixups (type 3 texture fetch constant, type 8 shader
  constant). Sampler map: u32 1, u32 8, eight slots (-1 none, -2 unused), u32 1, shader count. Shader names
  `shaders\track\...`. Vertex packing for track meshes: not documented anywhere.

## Placements (`.pvs`)

- **Verified (FM3):** `Media/Tracks/<track>/Ribbon_NN/<track>_NN.pvs`, magic `FPVS`, version **24** (FM4 27, FH1 50); the
  next words match the FM4 header (u32, u32, then u16 ribbon = layout number). Ladera has 20 ribbons; the model and
  texture tables are the same in each, the instance lists differ. Read by [`tools/fm3_pvs.py`](tools/fm3_pvs.py):
  - **texture table** (found by its record-0 pattern): u32 count, 28-byte records: u32 texture id, u32 index
    (sequential), f32 scale x, scale y, offset x, offset y, u32 flags. Whole textures have (1, 1, 0, 0) and flags 0/1/4;
    lightmap entries have scale 1/16 and flags 8/9/12, and their offsets step through a 10 x 10 grid (pitch 0.09375).
  - shader names: u32 count, strings (u32 length + `shaders\track\...`).
  - **instances**: u32 count, **56-byte** records (not FM4's 68): u16 model, u32 flags, u32 lightmap (texture-table
    index), u32, u32, u16, u16[3] LOD distances (half), f32[3] position, u16[9] rotation 3x3 (half, row-major).
  - **models**: u32 count; vec u32 texture-table indices, vec u32 shader indices, f32[16] matrix, f32[4] extent. Model i
    is `<prefix>out.<i:05d>.rmb.bin`.
- **Texture link (verified against a captured frame):** the model file's `shaders\track\*` names end in their texture
  count (`diff_spec_refl_norm_4`); in mesh-material order each shader takes the next block of the model's whole-texture
  entries, and the first of a block is the base texture (140 of 165 checks right). The model's lightmap is its entry with
  scale 1/16: **when `_0x<id>.bix` exists it is a whole lightmap texture** (the rectangle is unused; UV1 or UV0 as
  decoded); **otherwise it is a slot in an `.stx.bin` atlas**: the atlas whose id is the largest atlas id <= the entry's
  id, UV = (UV1, or UV0) * scale + offset, with the mesh's UV tile and offset applied first. Instanced models take the
  lightmap from each instance's own entry instead (often the next table entry). 46 + 48 of 50 + 51 captured meshes
  follow this.
- **Instance placement (verified):** world = F (R^T p + pos) with F = diag(1, 1, -1), p the model-file vertex, R the
  instance's 3x3 (half floats), pos its position; instances at the origin carry R = F (identity). All 144 captured
  placements of instanced props match within 2 cm. Instance sets differ per layout (ribbon): Ladera's Ribbon_00..09 have
  `.pvs` files (10..19, the reverse layouts, only cameras), and the grid capture's props are explained by Ribbon_04/05.
  Model files without instances are world-space track pieces, drawn in every layout. Instance LOD distances: 80/160/240
  m for barriers, -1 (always) for vegetation.
- TrackSettings.xml (per track) holds the fog (near 80, far 1600, colour), ambient and SH lighting, desaturation and the
  sky offset; the frame's pixel-shader constants carry the same values (c247 ambient (0.14, 0.14, 0.18), c248 sun
  (1.58, 1.57, 1.5), c242 fog colour).
- **FM4 v27 (fm4_pvs.py `read_fm4`), to adapt:** header (u32, u32), u16 ribbon, u16 a2, then cells, textures, shaders,
  instances, models, always, models_a, models_b, dynamic, prefix, two u8, names, cell lists. `vec` = u32 count + items;
  string = u32 length + bytes. Texture record 28 bytes (u32, u32, f32 x4, u32). **Instance (68 bytes):** u16 model, u32
  flags, u32 idx, u32, f32 x4, u16, u16 x3 LOD, f32 x3 position, u16 x9 rotation (half floats, 3x3). **Model:** vec u32
  textures, vec u32 shaders, f32 x16 matrix, f32 x4 extent. Instance flags: bit 1 transparent, bit 2 opaque, bit 4
  mirror, bit 9 cube map, bit 28 decal; LOD distances per instance.

## Textures

- **ForzaStudio-EVO `XdsTexture.cs`:** `.xds` = 13 big-endian dwords (dword 0 == 3, dword 1 == 1), fetch constant in
  dwords 7-12: d7 bit 31 tiled, bits 22-30 pitch / 32; d8 bits 0-5 format (18/51 DXT1, 19/52 DXT3, 20/53 DXT5, 49 DXN,
  59 DXT5A, 6/50 A8R8G8B8), bits 6-7 endian, bits 12+ base page (4 KiB); d9 width-1 bits 0-12, height-1 bits 13-25; d11
  bits 6-9 max mip; d12 bit 11 packed mips, bits 12+ mip page. Untiling (`XenosTiling.cs`, after Xenia):
  outer = (((y>>5)*(pitchBlocks>>5)) + (x>>5)) << 6; inner = (((y>>1)&7)<<3) | (x&7); b = (outer|inner) << log2(bpb);
  bank = (y>>4)&1; pipe = ((x>>3)&3) ^ (((y>>3)&1)<<1); offset = ((y&1)<<4) | (pipe<<6) | (bank<<11) | (b&0xF) |
  (((b>>4)&1)<<5) | (((b>>5)&7)<<8) | ((b>>8)<<12).
- **FH1/FM4:** `.xds` = 52-byte D3D texture header whose last 24 bytes are the GPU fetch constant (dword 0 bit 31 tiled,
  bits 22-30 pitch / 32; dword 1 bits 0-5 format, 6-7 endian; dword 2 width-1 / height-1 in 13-bit fields), then
  Xenos-tiled, byte-swapped data. DXT1 = 18, DXT5 = 20 (51/53 load as 18/20).
- **`.bix` (verified, [`tools/fm3_tex.py`](tools/fm3_tex.py)):** `_0x<id>.bix` = 28-byte header + mip chain,
  `_0x<id>_B.bix` = base level. Header (big-endian u32): `BIX0`, width, height, mip count, format word (low byte =
  Xenos format | endian << 6, as the fetch constant's dword 1; e.g. 0x1A200154 = DXT5, endian 1), mip-chain size,
  base-level size. Data Xenos-tiled with the pitch = width (32-texel aligned), untiled with the formula above. 205
  textures decode identical to the captured frame's (maximum error 0); DXN normal maps differ only in the blue channel
  we fill.
- **`.stx.bin` (verified, `fm3_tex.load_stx`):** a CAFF container ("CAFF21.11.05.0034"): 0x190-byte header (.data size
  at 0x60, .gpu size at 0x88), .data, .gpu. In .data: one 128-byte record per texture (`texture` + `04.05.05.0032`, u32
  format word as BIX0 at +0x18, u16 width + u16 height at +0x24, mip count in the byte at +0x30), then the source file
  names (`...\compiled\_0x<id>_s.bin` = a 32-texel stream copy of `.bix` <id>, `_0x<id>_a.bin` = **lightmap atlas**
  <id>), then a 28-byte table per texture whose words 5 and 6 give the .gpu offset: (w5 & 0xFFFF) << 16 | w6 >> 16.
  Ladera: 1,062 stream copies and 24 atlases (512 x 512 DXT1, one DXT5); the captured atlases decode identically.
