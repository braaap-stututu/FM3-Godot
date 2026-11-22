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
  next words match the FM4 header (u32, u32, then u16 ribbon = layout number 0/1/2).
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
- `.bix`: streamed track textures; FH1 describes BIX1 with a 28-byte header (width, height, mips, format word, chain
  size, base size), base level in `_0x<id>_B.bix`, mips in `_0x<id>.bix`. **FM3 has BIX0** (e.g. 0x200 x 0x200, 10
  mips, word 0x1A200154): field order to verify.
- `.stx.bin` (CAFF container, `.data` + `.gpu` sections): per FH1, the track's **static texture pack** (entries = header +
  base level + mips; atlas tiles by rectangle), not geometry. Section table not documented.
- Untiling: no Xenos untiling code in these repos; ReGPU (`src/gpu/texture.cpp`) has it, and the capture tap already
  produces RGBA8 decodes of every texture a frame uses, which can be matched to file data by hash.
