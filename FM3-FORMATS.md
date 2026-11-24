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
| [FMdangaina/ForzaStudio-EVO](https://github.com/FMdangaina/ForzaStudio-EVO) (GPL-3.0, C#; after Mike Davis' Forza Studio 4.6) | **FM3 and FM4**: car `.carbin` (OBJ/FBX/glTF), `.xds` textures with Xenos untiling, FM3/FM4 track bins (`ForzaTrackBin.cs`, `ForzaTrackSection.cs`, `ForzaTrackSubSection.cs`, `ForzaVertex.cs`, `XdsTexture.cs`, `XenosTiling.cs`) | **Directly**: track mesh and vertex layout, UV transform, xds header, untiling. Not covered: `.pvs`, `.bix`, `.stx.bin`. Second pass (2026-11-23): the full FM3 car `.carbin` reader, car texture lookup, gamedb / strings / DLC / physics / sound (sections below; docs in its `docs/`: `CARBIN_ALL_GAMES.md`, `CARBIN_FROM_XEX.md`, `PORT_FM4_TO_FM3.md`, `FM3/`). No `TrackSettings.xml`, ribbon or `.pvs` code |
| [se7ensins "Big Forza modding thread"](https://www.se7ensins.com/forums/threads/big-forza-modding-thread-tuts-dls.916498/) (D3FEKT, 2013-2018, 61+ pages) | FM2-FM4 / FH1 tutorials and downloads | Not read: the host (and web.archive.org, archive.ph) is blocked from the cloud environment; only search snippets seen (see Community leads) |
| [Coupe5E/Forza3EU-Recomp](https://github.com/Coupe5E/Forza3EU-Recomp) | Another FM3 recomp | Not read |

For FM3 specifically, ForzaStudio-EVO is the one source with format code; nothing public covers `.pvs`, `.bix` or `.stx.bin`
(searched: GitHub repos, Nenkai's templates, Doliman100, hl360-forza3, FM4CarModelTools; archived Xentax threads and
web search were not reachable).

## Archives

- **Verified:** zip members use method 21 = Xbox LZX (`tools/fm3unzip`, the FM3 recomp's `src/lzx.cpp`).
- **ForzaStudio-EVO:** entries are LZX (21), deflate (8) or stored (0); xcompress.dll's `XMemCompress` with default
  LZX parameters reproduces the game's archives byte for byte. `Media\zipmanifest.xml` lists every game zip with
  `dirstart`, `dirsize`, `direntries`: a rewritten zip needs its line updated (`ZipManifest.cs`). Mount priorities
  (FM4, assumed for FM3): 65 DLC content, 80 game zips, 100 loose files, 250xx string tables, 100000 title updates.

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
- **ForzaStudio-EVO, the whole file as a parser** (`CarbinModel.cs`, `CarbinModelMotorsport3.cs`; reads all 3,930 FM3
  carbins of DVD1 to the last byte). A carbin is a serialized object tree: every object starts with a u32 version
  (traced in FM4's xex, `CARBIN_FROM_XEX.md`). FM3 versions: body header 1, wheel header 2, brake header 1,
  ModelSettings **13** (FM4 16, FH 17, FM2 713/714: the reliable game test), shader version 11, part 2, mesh material
  settings 2, mesh 2, vertex buffer 2, index buffer 3.
  - **Header:** u32 type (1 car / brake, 2 wheel); u32 at 4 = 0xD on brakes. Length = 8, + 0x100 (type 1) or 20
    (type 2) unless the word at 4 is 0xD, + 8, + u32 N + N x 140-byte exhaust emitter records (version 2, type,
    parent, two 4x4 matrices), + 0x1AC (driver anchors: steering wheel, hands, butt, shifter; LOD range; **4** analogue
    gauges = pivot vec4, axis vec4 stored as (-x, -y, z), max rotation; 2 unknown floats; ...). Files: `<car>.carbin`
    (LODs 1-5), `<car>_lod0.carbin`, `<car>_cockpit.carbin`.
  - **Draw lists:** u32 n, then 2n lists (u32 count + entries `(part << 16) | mesh`): per LOD the see-through pass, then
    per LOD the opaque pass. FM3 see-through materials (0 exceptions on 3,810 files): window, glass, red_glass,
    detail_glass_clear/red/amber, blur_rim, chrome_blur_rim.
  - Then u32 1 (container version), u32 part count, parts, and a 24-byte trailer (`00000001 00000000` x 3: empty lists).
  - **Part (CCarSubModel / CCarPartData):** u32 2; 9 f32 bounds = origin, min, max (min/max relative to the origin);
    0x1C bytes (mass, centre of mass x3, detach damage (0.2 on mirrors / wings / bumpers that can fall off), 2 versions);
    u32 count + vec4 glass-shard vertices; u32 1; u32 count + u16 shard indices (main file glass only); two words
    (first byte = HasTransparentMeshes; FM3 has no extra `Pre` word as FM4); name (u32 length + ASCII); u32 2 + vertex
    buffer (count, stride, data) for LODs 1-5; u32 1 + u32 mesh count + meshes; u32 2 + LOD0 vertex buffer. **FM3 parts
    end there** (FM4 adds morph tables).
  - **Mesh (CCarMesh):** 9 bytes (material settings version 2, RemoveFromShadow bool, version 2); material name (u32
    length); u32 LOD; u32 primitive (6 strip, 0xFFFF restart / 4 list); 56 bytes = u32 material index + UnpackingData
    (version 1, PositionOffset, PositionScale, UVOffsetScale vec4s; identity on FM4 DLC); u32 3; u32 index count; u32
    index size (2/4); indices; u32 mesh flags.
  - **Vertex, 40 bytes (car parts):** 0 half4 position; 8 UV0 (2 halves, raw, no per-mesh normalisation); 12 UV1 (2
    halves); 16 normal, packed 11:11:10 (x bits 0-10 / 1023, y 11-21 / 1023, z 22-31 / 511, signed); 20 baked lighting
    (8 bytes, FM4's SH0); 28 damage word (same 11:11:10 packing, a direction with a weight 0..1, scaled by the shader;
    `000003FF` = does not move); 32 unknown; 36 bitangent 11:11:10 (EVO negates it). **16 bytes (brakes):** position,
    UV0, normal at 12 (model space, bounds 0). **44 bytes (wheels):** position, UV0, normal at 12, lighting at 16,
    then constants. No tangent on these two: EVO rebuilds it from UVs.
  - **Position per EVO = origin + (min + max) / 2 + xyz * w.** `tools/fm3_car.py` uses `xyz * w + offset` (matches
    captured draws). **To check:** the two agree only when the bounds are symmetric; compare on a part whose
    min != -max (the shader's c190 may already include the centre).
  - Two FM3 sections (FER_250GTO_64 glassRHL, FER_GTO_84 headlightRdown) have about +-1.7e38 in their bounds: skip them.
  - Wheels: FM3 wheels have no morph table. Aftermarket wheels (`List_Wheels.IsStock = 0`) model LOD 0 at a 15-inch
    reference and are scaled at run time; stock wheels are true size.
- **FH1/FM4:** strings are `u32 length + bytes`; `array<T>` = `u32 version(1), u32 count, T...`; root u32 (5 car, 3 wheel,
  1 part); CMesh = material/technique name, u32 LOD, u32 primitive (6 strip / 4 list), u32 material index, unpacking
  data, index buffer (FM4 v3: count, format 2/4); VertexBuffer v3 = version, count, stride, flags (bit 0 key follows,
  bit 1 data not in file), [key], data. FM4 car vertex, stride 32: 4 x s16 position (normalised, scaled by the
  unpacking data), 2 x u16 UV1, 2 x u16 UV2, 4 x s16 tangent-frame quaternion, 4 x s16 SH0 (baked light). Morphs:
  u32 FMT_10_11_11. Textures bound by sampler name (textures.xml), not stored in the carbin.

- **Verified on this PC's files (2026-11-23, `tools/fm3_carbin.py`, a structural reader after the layout above):**
  every file reads to its last byte: 510 of 510 main carbins (`work\assets\carbins`), 567 of 567 wheel carbins, and the
  CR-X's / Eclipse's whole zips (main, `_lod0`, `_cockpit`, 8 brakes each). Corrections and answers:
  - **After the shard indices FM3 has a u32 and one byte**, not two words; the name's length then starts unaligned
    and so does the rest of the part (CR-X caliper: u32 0, byte 1, u32 9 `caliperLF`).
  - **Position:** all 18,444 parts have symmetric bounds (min = -max), so EVO's origin + (min + max) / 2 + xyz * w and
    the old origin + xyz * w are the same; identical to the old reader within 6e-8 m. Question settled.
  - **Index buffers of 4 bytes (LOD 0 files) restart strips with 0xFFFFFF**, not 0xFFFFFFFF or 0xFFFF (the Xenos's
    24-bit index limit); a strip reader that only knows 0xFFFF drops every LOD 0 mesh.
  - **Normals (byte 16, 11:11:10 signed, x in the low bits, big-endian word): confirmed**, |cos| 0.965 per vertex
    against normals rebuilt from the CR-X's LOD 0 geometry, pointing outwards (other decodings: 0.79 or less).
  - `_lod0.carbin` holds the exterior in detail (CR-X 31 parts, 103,628 vertices); the cabin, seats, steering wheel,
    mirrors, hood and the windscreen / side glass are only in the main file (LOD 1). `_cockpit.carbin`: 21 parts.
  - Material names in LOD 0 carry a `_lod0` suffix for some techniques (`tail_light_lod0`, `reverse_light_lod0`).
  - Car zips of Disc 2 / DLC cars sit inside the DLC packs as `media/cars/<Car>/...` (e.g. `0013_pri_65.zip`:
    MAZ_AxelaSport_05, MIT_EclipseGTS_03); `fm3unzip <pack> <out> <lowercase name>` extracts them.

## Car materials and textures (ForzaStudio-EVO)

- **Material name = shader technique name** (cockpit model: `cockpit_` + name first; unknown names fall back to
  `missing`, drawn black). FM3 techniques: `Media\Shaders\Cars\shaders_v11.fxobj` (+ DropShadow), 185 techniques; 51
  of 54 car LOD0 materials and all 55 cockpit ones have one (missing: `01___Default`, `4_MER_SLR_05_damage`, `body2`).
  Lists of what FM3 cars use: EVO `docs/FM3/MaterialUse.txt`, `PartMaterials.txt`, `SsParams.txt`, `SsUse.txt`.
- **Texture lookup** (`ShaderTextures.cs`; verified on FM4 and FH1, assumed for FM3): the technique's pixel shaders
  name their samplers in their D3D constant tables inside the `.fxobj`; `Media\cars\Shared.zip\textures.xml` maps each
  sampler to a file in the car zip (`%CARFOLDER%`), Shared.zip (`%SHAREDCARFOLDER%`) or the wheel folder, chosen by
  `loadFlags` (LOD15 = main model, LOD0, Cockpit, SuperLOD = showroom; terms joined by `&`, `!` = not). Built in:
  `baseSampler` -> `nodamage` / `damage` (+ `_LOD0` for close-up files). Cockpit parts sit on `Interior_LOD0.xds`
  (CockpitInteriorHiSampler). Effect layout notes: technique record 5 dwords (name ref, pass count, ?, ?, first pass
  ref), pass record 5 dwords (name ref, 0, pass block ref, 2 state refs); the pass block ends with FFFFFFFF, VS ref, PS ref.
- **Constant tables, verified (2026-11-23, `tools/fm3_fxobj.py`):** `shaders_v11.fxobj` holds 137 D3DX constant
  tables (92 pixel, 45 vertex shaders), big-endian, **without a 'CTAB' tag**: header u32 Size = 0x1C, Creator,
  Version (0xFFFF03xx / 0xFFFE03xx), Constants, ConstantInfo, Flags, Target; 20-byte constant records (name, register
  set, register, count, type info, default value offsets). They name every register, with defaults. The defaults are
  only fallbacks: the game sets runtime values (paint SpecularPower 75 in the capture, default 128), so **the captured
  constants named by these tables are the truth**. Window glass (PS `b117fbafcc1fa980`, all 70 window draws of the
  grid capture): GlassColor c219 = (0, 0.07, 0.06, 0.1), GlassMaxOpacity c218 = 1, FresnelMin c189 = 0.4, FresnelMax
  c190 = 1, FresnelScale c191 = 1, FresnelPower c216 = 1.5, CubeScale c217 = 1, reflectionScaler c192 = 1,
  SpecularAmount c116 = 0, Static / DynamicEnvLightmapDampner c180 / c119 = 0.5 / 0.3. Car paint (PS
  `e41e183a423e6f1b`): CubeScale c224, FresnelMin/Max/Scale/Power c219-c222, SpecularAmount c180, SpecularPower c189.
  No car's `shadersettings.xml` overrides the window technique (8 grid cars checked).
- **Per-car parameters:** `shadersettings.xml` in the car zip, one entry per technique (`cockpit_` + material for the
  cockpit). FM3: 246 of 311 cars have one; 45 techniques set 64 parameter names, some misspelt (`GuageEmissiveScale`,
  `CokpitBumpScale`, `CockpiSpecularAmount2`); FM3-only: CarbonFiber*, CubePower, DamageSpecularKillAmount,
  Ghost*Distance, TrackLightmapWVPS, ...
- **Colour space:** FM3 car textures hold **sRGB values without the gamma flag** (fetch dword 0 low byte 0x02, plain
  DXT1/DXT5 formats 0x52/0x54); FM4 re-encodes for the 360 gamma curve (0xFE, AS_16 formats). So sample FM3 colour
  textures as sRGB. **Normal maps are DXT1** (r = x, g = y, b = z), not DXN.
- Wheel zips (`Media\Wheels\*.zip`) add `wheel0_lod0.xds`..`wheel3_lod0.xds`. Car thumbnails: `Media\UI\Textures.zip`
  `Thumbnail_<Id>.xds`, 512 x 256 A8R8G8B8, 2 mips.

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
- **The track shaders themselves (2026-11-24, `tools/fm3_trackshader.py`):** each track zip carries its shaders as
  `shaders\track\<NAME>.fxobj`, holding Xbox 360 shader containers (big-endian): u32 magic (`0x102A1100` pixel,
  `0x102A1101` vertex), u32 data offset, u32 data size, u32 0, u32 0x24, u32 info offset, u32 code-info offset, u32 0;
  the D3DX constant table at +0x28 (names every parameter: `Blend_A_uvOS` = c120, `TextureMap_4903Sampler` = s0, ...);
  at code-info: u32 code offset within the data, u32 code size; the data starts with the literal constants (16-byte
  vectors numbered down to c255), then the Xenos microcode, the same code a capture holds (`fir_disasm.disasm`). So every
  track shader's exact formula is readable without a capture. Per file: several variants (with / without the shadow
  map, depth and lightmap-only passes); the plain one is the shortest full one without `TimeGain`. Texture coordinates
  are `uv * (cN.zw * c(param).xy) + cN.xy` (each sampler's uvOS c116-c124, the material parameter giving the scale);
  vertex fetch offsets are patched at load time (0 in the file), so which interpolant is which vertex UV pair is read
  from the meshes (the lightmap / value-map pair is the one within 0..1). Formulas found this way are in
  `tools/fm3_families.py` (overlay blend, three-layer value blend, the road blends, road lines: lerp(P0, line, road
  alpha) x P1.z with the line's own alpha, road-edge decals with a separate opacity map).
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
- Not geometry to draw as is: `flare_*` (the sun flare), `LGHT_*` meshes (light volumes, no material) and `OCCLUD_*`
  (occlusion geometry: RoadAmerica, Sebring, Mugello).
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
- **Sky textures (2026-11-24):** the sky dome (`<track>out.sky.rmb.bin`) has one material per mesh (sky1..sky5/6),
  slots 0..n-1; no `.pvs` model lists its textures: they are the last n `.pvs` texture entries with flags 1, in id
  order (streamed from the `.stx`; CrownJewel 3506-3511: sky1..4 = 3509/3510/3507/3508, matched against the captured
  sky at mean |diff| 3.5-6; sky5 the zenith cap, sky6 the landscape below the horizon). The sun: TrackSettings.xml
  `ShadowLightDirection` (game space; CrownJewel's equals the captured sun).

## Crowd (`<track>_track_NN.crowd`, beside each layout's `.pvs`; 2026-11-24)

Big endian. Header u32 version (2), u32 cells, u32 people. Cell (52 bytes): row start, end, middle (3 x f32 each),
f32 half length, u32 0, u32 first person, u32 people. Person (16 bytes): u16 figure (low byte 0..14, +256 a second
set), 6 zero bytes, the offset from its cell's middle as three half floats (metres), the facing angle as a half float
(radians: 0, pi/2, pi, 3pi/2 common). Coordinates are in the glTF frame of our exports (no z mirror: the cells lie on
the track's own 'crowds' cards). CrownJewel Ribbon_04: 95 cells, 2627 people, each within a few metres of its cell's
row. `fm3_track_export.py` draws them as cards from the 'crowds' sprite sheet (seven seated figures).

## Textures

- **Track textures as their own CAFF (2026-11-24):** besides `_0x<id>.bix` + `_B.bix` pairs, a track's bin.zip has
  `_0x<id>.bin` files (290 on CrownJewel): a CAFF container (as the `.stx`) with one texture record (format word
  at +0x18, width / height at +0x24, mip count at +0x30) and its GPU data right after the .data section. The `.stx`
  stream entry for the same id is a smaller copy (the grandstand canopy: 64 x 64 here, 32 x 32 in the stream).
  `fm3_tex.load_caff_texture`. Material parameters can scale UVs per shader: `diff_spec_ovly_2` tiles its base by
  parameter 0's xy (15, 60); road lines (`rdline_*`) use parameter 0 as a colour.

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

## Game data (ForzaStudio-EVO, 2026-11-23)

Not geometry, but what the game logic needs. FM3 title ID 4D53084D (FM4 4D530910). Points EVO marks unverified are
said so.

- **Database:** `Media\DB\gamedb.slt`, plain SQLite, 176 tables (list = keys of EVO `docs/FM3/IdMax.json`; relations
  `docs/FM3/DbRelations.tsv`; FM4 schema `docs/GAMEDB_SCHEMA.md` mostly applies). FM3 = has `Data_Car` and
  `CarClasses`, no `Data_Motor` (FM4) or `EventHubs` (FH). Every car table keys on `Ordinal` = `Data_Car.Id`; per-car
  rows are `car * 1000 + n`; `MediaName` is unique and names the car zip. FM3-only: `List_TorqueCurve` with a
  zero-throttle curve, `Data_Car.GaugeID -> List_DigitalGauges`, `ChampSeries`, `CareerGridOrdering`, `GameTypes`,
  `Tuning_Options`, `List_UpgradeEngineCSC/DSC/Manifold`; 8 engine-upgrade levels (FM4 4); `CarPartPositions` parts
  0-8 (part 4 + `CameraOverrides.CamCockpitOffset` = cockpit eye); `Tracks` has no `IsReverse`. Sizes: 415 cars
  (Id 247..1215 base), 431 engines, 53 makes, 109 tracks, 33 environments, 221 events, 910 races.
- **Strings:** `Media\StringTables\<LANG>.zip` (16 languages), one `.str` per table. A text column holding `_&<uint>`
  = table id (high 16 bits) + key (low 16). `.str` = "LSB2", big-endian: header `LSB2, 1, 2, 0x24, 4, 0x24`, section
  offsets B/C/D at 0x18/0x1C/0x20; section A at 0x24 (length, count at 0x28, 6-byte entries from 0x2C: u16 key, u32
  offset in UTF-16 units, sorted, FFFF end), then zero-terminated UTF-16BE text. The game reads only A. (Measured on
  FM4/FH2, assumed for FM3.)
- **Car zip** `Media\cars\<MediaName>.zip`: the three carbins, brakes `_caliper??` / `_rotor??.carbin` (no `_lod0`
  suffix in FM3), `*.xds`, `shadersettings.xml`, `carattribs.xml`, `physics\maxdata.xml` (collision: a bevelled box
  + spheres), `masks.xml`, `liverymasks\*.tga`. Digital dash separate: `Media\DigitalGauges\Dash_<car>.zip`
  (`.fbf` v0x3EE, `.bgf`, `.bsg`), images in `UI\Textures.zip` `UI4/Dashboards/<CAR>/`; 154 dashes.
- **Physics** (all in gamedb except `Media\Physics\PI.xml`; EVO `Fm3Perf.cs`, `docs/FM3/PI_AND_RATINGS.md`): torque =
  stock `List_UpgradeEngineCamshaft` (RedlineRPM, TorqueCurveMaxRPM, NumRPMEntriesArray, TorqueCurveFullThrottleID /
  ZeroThrottleID) -> `List_TorqueCurve` v0..vN x TorqueScale x 0.01 (looked up as if n points spanned n-1 intervals),
  times 1 + sum(TorqueScale - 1) of the stock engine-part rows + turbo / supercharger RobScale. Gears:
  `List_UpgradeDrivetrainTransmission.GearRatio0..` (NumGears includes reverse = GearRatio0); drive type
  `Data_Drivetrain.DrivetypeID` 1 FWD / 2 RWD / 3 AWD. Tyres: `List_TireCompound` -> `List_TireFrictionMultiCurve` ->
  `List_TireFrictionCurve`, width and brand scales, axle scales from `List_UpgradeCarBodyChassisStiffness`. Mass
  `List_UpgradeCarBodyWeight.Mass` (kg / 100); CG height `CMHeight` + mean `DefRideHeight`; aero `List_AeroPhysics`.
  PI is a simulated lap over `PI.xml`'s 15 segments (MinPITimeSeconds 97.4, MaxPITimeSeconds 159.1). FM3 vs FM4:
  `docs/FM3_GRIP_CM_SPRINGS.md` (FM3 CM ~0.17 m lower, stiffer springs, steering x 1/1.2, no camber change on
  independent axles).
- **Engine sound:** `Media\Audio\cars\Engines\EngineTuning.zip` `<Data_Engine.MediaName>_ET.xml` (idle / redline rpm,
  cylinders, Exhaust / EngineIntake / EngineAmbient upgrades L0..L3 -> `*_HT.xml`) -> `HarmonicTuning.zip` `*_HT.xml`
  (`<Soundbank name="x.fsb">`, `<Loop wavebankindex rpm_min rpm_sample rpm_max>`) -> `Engines\Soundbanks\LOD1\*.fsb`
  (FSB4, 0x30 header; some DLC FSB3, 0x18; XMA audio, mode flag 0x01000000). `Audio\cars\CarModelTuning.zip`
  `<car>_CMT.xml`: listener / chassis positions. Music: `Media\audio\Music\*.xma` + `*Playlist*.xml`, separate intro
  files.
- **DLC packs:** folder `4D53084D0CCF` + offer as 4 hex digits; `Media\DLCZips\zipmount.xml`, `stringtables.xml`, a
  priority-65 content layer, a full replacement string table, `db\patch\<offer>005_merge.slt` (rows replace by key,
  cannot delete), `Media\LicenseMasks\00000001.sql`.

## Community leads (2026-11-23, search snippets only)

The se7ensins thread (above) could not be read; from search snippets and related results:

- Gamedb edits with a SQLite browser (car specs, body parts, tyre width); a patch of the `default.xex` database check so
  a modded gamedb loads (users report version errors); `zipmanifest.xml` edits in a decrypted xex to add models.
- Tunable INI files: `PhysicsSettings.ini` (camber), `GameTunableSettings.ini` (sell prices), `CameraSettings.ini`.
  **To check** which FM3 ships in `Media`: game-feel constants for the game logic.
- Tools named: QuickBMS with a Forza zip script, Forza Studio, a hex editor.
- Save / profile format lead: [X3T-Infinity Forza Save Editor](https://x3t-infinity.com/Forza) (FM3, FM4, FH1, FH2;
  Xenia; v3.2.0.0, 2023), closed source.
- FM3 threads: [How to modify FM3 car specs](https://www.se7ensins.com/forums/threads/how-to-modify-forza-motorsport-3-car-specs.537035/),
  [FREE Forza 3 Mod Tool](https://www.se7ensins.com/forums/threads/free-forza-3-mod-tool.334387/).
- [FMdangaina/ForzaEditor](https://github.com/FMdangaina/ForzaEditor): same author, likely an earlier ForzaStudio-EVO.
