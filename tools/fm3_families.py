"""fm3_families.py: FM3 track shader families -> render recipes for the viewer (godot/viewer/fm3_blend.gdshader).

Worked out from the captured frame (tools/fm3_shaders.py: per hardware slot, the material slot it reads and its UV
transform) and the pixel shaders' disassembly (tools/fir_disasm.py --pixel). The pixel shader's constants c0..cN are
the material's parameter vectors (fm3_track._parse_materials); hardware slot k reads material slot k; slot 7 is the
lightmap. All UV pairs are u16 pairs decoded with the mesh's UV tile and offset (fm3_track.uv_pair).

  terrain blend (terr_blnd_spec_3, terr_2_blnd_spec_3, shldr_blnd_spec_3, road_blnd_diff_spec_3, ..._vclr_...):
      albedo = lerp(t0 * tint0, t1 * lerp(1, tint1, vertex alpha), t2.r)
      t0 at UV_a * P[k].xy, t1 at UV_b * P[k+1].xy, t2 (mask) and the lightmap at UV_c; P[k] is the material's
      specular vector (z = intensity, w = power), tint0 = P[0] when k > 0, tint1 = P[k+2] (vertex-colour variants).
      UV_a, UV_b, UV_c: the u16 pairs from byte 16 (stride 24: a = b = 16, c = 20; stride 28: 16, 20, 24; stride 32
      with vertex colour (ARGB at byte 20): 16, 24, 28).
  curb (shldr_road_blnd_spec_3): t0 at UV0 * lerp(P[0].rgb, 1, t1.g at UV1) (disassembly of ps aa004de7).
  refl (diff_spec_refl_norm_4, diff_spec_refl_3: windows): t0 at UV0 * P[0].yz lit by the lightmap, plus the
      environment reflection * t0.a * P[0].x (disassembly of ps f4e339d2; the viewer stands in a sky gradient for the
      game's cube map).
  road (road_blnd_2, road_4clr_blnd_2): t0 = a grain texture in world space (x, z) * P[1].x,
      t1 = the surface (marks, patches) at UV0; albedo = t1 * 0.34 * grain / mean(grain) (0.34 calibrated against the
      game's screenshot, as profiles/fm3/materials.json's asphalt).
  paint (shldr_4clr_blnd_mask_2): grain as road; the paint mask is t1's alpha at UV0; albedo = lerp(0.16 * grain,
      P[2].rgb * 0.75 + sheen, mask) (the capture rule for this shader, profiles/fm3/materials.json).
  Not seen in the capture, inferred from their textures (slot 0 asphalt grain, slot 1 tyre-mark multiplier, slot 2
  dirt, slot 3 channel mask: red high on the asphalt, low at the edges) and the captured rdedg_..._ovly_blur_4 shader:
  road (road_blnd_diff_spec_3): as road, grain at world (x, z) * P[0].x.
  edge (rdedg_blnd_diff_spec_bump_4, stride 36): lerp(dirt, road, mask.r); UV0 (marks, dirt * P[3].xy) at byte 16,
      the 0..1 edge mask at 20, the lightmap at 24.
  mix (shldr/terr_blnd_spec_vclr_mix_3): lerp(slot 0 at UV0 * P[0].xy, slot 3 at UV0 * P[3].xy, slot 2 mask.r);
      UV0 at byte 20 (16 is a vertex colour), mask and lightmap at 24.
  (Those UV0 offsets: the one u16 pair with the same density in every mesh, 0.143 UV per metre.)
"""
import re

BLEND = re.compile(r'^(terr_(2_)?blnd_spec_(3|vclr_3)|shldr_blnd_spec_3)')
ROAD = re.compile(r'^(road_blnd_2|road_4clr_blnd)')
CURB = re.compile(r'^shldr_road_blnd')
ROAD_DIFF = re.compile(r'^road_blnd_diff_spec')
EDGE = re.compile(r'^rdedg_blnd_diff_spec_bump')
MIX = re.compile(r'^(shldr|terr)_blnd_spec_vclr_mix')
PAINT = re.compile(r'^shldr_4clr_blnd_mask')
REFL = re.compile(r'^diff_spec_refl_(norm_4|3)$')
OVLY = re.compile(r'^road_diff_spec_ovly_2$')
BLEND3 = re.compile(r'^terr_blnd_spec_norm_5$')
ROAD3 = re.compile(r'^road_3clr_blnd_2$')
SHEEN = (0.1, 0.13, 0.17)


def recipe(shader, params, stride, slots):
    """A render recipe dict for a mesh's material, or None (then the plain base texture is used)."""
    if not shader or not slots:
        return None
    vclr = 'vclr' in shader
    if BLEND.match(shader):
        pairs = [o for o in range(16, stride - 3, 4) if not (vclr and o == 20)]
        if len(pairs) < 2 or len(slots) < 3 or min(slots[:3]) < 0:
            return None
        # (the specular vector's intensity: 0.2..1.2 on CrownJewel, 1.5 on Catalunya's verges, 2.0 on AmalfiGP; above
        # 1.0 the recipe used to be skipped and the verge drew its slot 0 alone: gravel where the game has lawn)
        k = next((i for i, p in enumerate(params) if 0.05 <= p[2] <= 4.0 and p[3] >= 5), None)
        if k is None:
            return None
        tint0 = list(params[0][:3]) if k > 0 else [1.0, 1.0, 1.0]
        s1 = k + 1
        tint1 = list(params[k + 2][:3]) if (vclr and k + 2 < len(params)) else [1.0, 1.0, 1.0]
        if k == 0 and len(params) > 2 and abs(params[1][3] - 1.0) < 1e-3 and params[2][2] == 0.0:
            # shldr_blnd_spec_3 (disassembled, SHLDR_BLND_SPEC_3.fxobj): lerp(A, B * P[1].rgb, v), A at UV * P[0].xy,
            # B at the same UV * P[2].xy (P[1]: (1,1,1) on CrownJewel, greys and browns on Catalunya)
            tint1, s1 = list(params[1][:3]), 2
        return {'mode': 'blend', 'src0': pairs[0], 'src1': pairs[1] if len(pairs) >= 3 else pairs[0],
                'mask': pairs[-1], 'lm': pairs[-1], 'vclr': vclr and stride == 32,
                'scale0': list(params[k][:2]), 'scale1': list(params[s1][:2]) if s1 < len(params) else [1.0, 1.0],
                'tint0': tint0, 'tint1': tint1, 'slots': slots[:3]}
    pairs = list(range(16, stride - 3, 4))
    if REFL.match(shader) and slots and slots[0] >= 0 and params and pairs:
        # windows and glazing (diff_spec_refl_norm_4 / diff_spec_refl_3; captured ps f4e339d2): the SPEC mask t0 (slot 0)
        # at UV0 * P[0].yz, its alpha x P[0].x the environment cube's reflection; the colour is the Diffuse texture,
        # material slot 2 at UV0 * P[1].xy (the shaders' constant tables, every track; until 2026-11-25 the SPEC mask was
        # drawn as the colour: MapleValley's glass office front a dark wall)
        diff = slots[2] if len(slots) > 2 and slots[2] >= 0 else slots[0]
        return {'mode': 'refl', 'src0': pairs[0], 'src1': pairs[0], 'mask': None, 'lm': None, 'vclr': False,
                'scale0': list(params[0][1:3]), 'scale1': list(params[1][:2]) if len(params) > 1 else [1.0, 1.0],
                'tint0': [params[0][0]] * 3,
                'tint1': list(params[2][:3]) if len(params) > 2 else [1.0, 1.0, 1.0],  # reflection tint (teal glass)
                'slots': [slots[0], diff], 'has_diffuse': diff != slots[0]}
    if shader in ('shldr_blnd_3', 'terr_blnd_3', 'terr_blnduv2_spec_3') and len(slots) >= 3 and min(slots[:3]) >= 0             and len(params) >= 3 and stride >= 28:
        # Disassembled (tools/fm3_trackshader.py): albedo = lerp(A, B, value) with per-shader parameters; UV pairs: A 16,
        # B 20 (terr_blnduv2: 16), value 24 (terr_blnduv2: 20), lightmap 24
        #   shldr_blnd_3: A * P[0].xy, B * P[2].xy tinted P[1].rgb, all x P[0].z (RoadAmerica, Sebring, Tsukuba, RoadAtlanta)
        #   terr_blnd_3 / terr_blnduv2_spec_3: A * P[1].xy tinted P[0].rgb, B * P[2].xy (LagunaSeca, AmalfiGP, Motegi)
        if shader == 'shldr_blnd_3':
            g = params[0][2]
            sc0, sc1, t0, t1 = params[0][:2], params[2][:2], [g] * 3, [params[1][i] * g for i in range(3)]
        else:
            sc0, sc1, t0, t1 = params[1][:2], params[2][:2], list(params[0][:3]), [1.0, 1.0, 1.0]
        uv2 = shader == 'terr_blnduv2_spec_3'
        return {'mode': 'blend', 'src0': 16, 'src1': 16 if uv2 else 20, 'mask': 20 if uv2 else 24, 'lm': 24, 'vclr': False,
                'scale0': list(sc0), 'scale1': list(sc1), 'tint0': t0, 'tint1': t1, 'slots': slots[:3]}
    if shader in ('road_2blnd_uv3_3', 'road_2blnd_3') and len(slots) >= 3 and min(slots[:3]) >= 0 and len(params) >= 4:
        # Disassembled: grain g (slot 0) at world (x, z) * P[1].x, colour c (slot 1) at UV 16 * P[1].yz, value v = slot
        # 2's green at the lightmap's UV * P[3].xy (uv3_3: 16, else 20)
        #   road_2blnd_uv3_3 (RoadAmerica): lerp(g.a * P[0], (g + P[2]) * c, v)
        #   road_2blnd_3 (RoadAtlanta, Sebring, Sunset): g * P[0] + v * c * (g + P[2] - g * P[0])
        uv3 = shader == 'road_2blnd_uv3_3'
        return {'mode': 'road2u' if uv3 else 'road2', 'src0': 'xz', 'src1': 16, 'mask': 16 if uv3 else 20,
                'lm': 16 if uv3 else 20, 'vclr': False, 'scale0': [params[1][0]] * 2, 'scale1': list(params[1][1:3]),
                'scale2': list(params[3][:2]), 'tint0': list(params[0][:3]), 'tint1': list(params[2][:3]), 'slots': slots[:3]}
    if shader == 'rdedg_diff_opac_2' and len(slots) >= 2 and min(slots[:2]) >= 0 and len(params) >= 2 and stride >= 28:
        # road-edge decals (disassembled): t0 at UV 16 * P[0].xy, opacity = t1.a at UV 24 * P[1].xy, the lightmap at 20;
        # drawn as an opaque t0 they were solid strips along the track edges (fm3_blend_alpha.gdshader)
        return {'mode': 'opac2', 'src0': 16, 'src1': 24, 'mask': None, 'lm': 20, 'vclr': False,
                'scale0': list(params[0][:2]), 'scale1': list(params[1][:2]), 'tint0': [1.0, 1.0, 1.0],
                'tint1': [1.0, 1.0, 1.0], 'slots': slots[:2]}
    if shader == 'rdline_blnd_diff_spec_opac_3' and len(slots) >= 3 and min(slots[:3]) >= 0 and len(params) >= 3 and stride >= 24:
        # NewYork's road lines (disassembled): as rdline_blnd_spec_opac_3, but the opacity is a third texture's alpha
        # (Opacity_Map, slot 2 = material slot 3 here, at UV 16 * P[2].xy); drawn opaque they were bright white bars
        return {'mode': 'rdline3', 'src0': 16, 'src1': 20, 'mask': None, 'lm': 20, 'vclr': False,
                'scale0': list(params[1][:2]), 'scale1': [1.0, 1.0], 'scale2': list(params[2][:2]),
                'tint0': list(params[0][:3]), 'tint1': [params[1][2]] * 3, 'slots': slots[:3]}
    if shader in ('rdline_blnd_diff_opac_2', 'rdline_blnd_spec_opac_3') and len(slots) >= 2 and min(slots[:2]) >= 0 and len(params) >= 3 and stride >= 24:
        # road lines (both disassembled, the same code): lerp(P[0].rgb, t0, t1) * P[1].z, t0 at UV 16 * P[1].xy (opacity
        # t0.a), t1 (material slot 1, the road alpha) at UV 20 * P[2].xy, the lightmap at 20. (rdline_blnd_spec_opac_3 was
        # fitted by eye before: alpha = the line's red, colour x 0.6 = what P[1].z is on Catalunya; CrownJewel's 0.8)
        return {'mode': 'rdline2', 'src0': 16, 'src1': 20, 'mask': None, 'lm': 20, 'vclr': False,
                'scale0': list(params[1][:2]), 'scale1': list(params[2][:2]), 'tint0': list(params[0][:3]),
                'tint1': [params[1][2]] * 3, 'slots': slots[:2]}
    if shader in ('diff_clr_spec_2', 'barr_shad_diff_clr_spec_2') and len(slots) >= 3 and min(slots[:3]) >= 0 and params:
        # palette-tinted props (tyre walls, wall pieces; disassembled): t0 * P[0].z * lerp(t0, palette, mask.a), t0 at UV 16
        # * P[0].xy, the paint mask (slot 1) at UV 16, the palette colour per instance (fm3_track_export: tint1)
        return {'mode': 'palette', 'src0': 16, 'src1': 16, 'mask': None, 'lm': 20 if stride >= 24 else None, 'vclr': False,
                'scale0': list(params[0][:2]), 'scale1': [1.0, 1.0], 'tint0': [params[0][2]] * 3, 'tint1': [1.0, 1.0, 1.0],
                'slots': slots[:2], 'palette_slot': slots[2]}
    if shader == 'shldr_blnd_spec_vclr_dualmix_4' and len(slots) >= 4 and min(slots[:4]) >= 0 and len(params) >= 5             and stride >= 28:
        # LeMans' verges and run-offs (disassembled, simplified): lerp(A * P[0], B * P[3], v) * vertex colour; A (slot 0) at
        # UV 20 * P[1].xy, B (slot 2) at UV 20 * P[4].xy, v = slot 3's green at UV 24 (also the lightmap's), the vertex
        # colour (ARGB) at byte 16. (The game also mixes each layer with a copy at a rotated UV by an offset map, slot 1,
        # against visible tiling: left out.)
        return {'mode': 'dualmix', 'src0': 20, 'src1': 20, 'mask': 24, 'lm': 24, 'vclr': True, 'vclr_at': 16,
                'scale0': list(params[1][:2]), 'scale1': list(params[4][:2]), 'tint0': list(params[0][:3]),
                'tint1': list(params[3][:3]), 'slots': [slots[0], slots[2], slots[2], slots[3]]}
    if ROAD3.match(shader) and len(slots) >= 2 and min(slots[:2]) >= 0 and len(params) >= 3 and stride >= 20:
        # road_3clr_blnd_2 (MapleValley's asphalt; disassembled): grain t0 at world (x, z) * P[1].x, v = t1.rgb * t1.a
        # (slot 1 at UV 16 * P[1].yz, the lightmap's UV); albedo = grain * P[0] + v * (grain + P[2] - grain * P[0]): dark
        # asphalt (P[0] 0.15) with lighter patches; drawn as the bare grain it was a garish leaf-litter picture
        return {'mode': 'road3', 'src0': 'xz', 'src1': 16, 'mask': None, 'lm': 16, 'vclr': False,
                'scale0': [params[1][0]] * 2, 'scale1': list(params[1][1:3]), 'tint0': list(params[0][:3]),
                'tint1': list(params[2][:3]), 'slots': slots[:2]}
    if BLEND3.match(shader) and len(slots) >= 4 and min(slots[:4]) >= 0 and len(params) >= 2 and stride >= 28:
        # terr_blnd_spec_norm_5 (AmalfiGP's cliffs and slopes; disassembled from TERR_BLND_SPEC_NORM_5.fxobj): v = the
        # blend value texture (slot 2) at UV byte 20; albedo = lerp(lerp(A, B, v.g), C, v.b) * v.r * P[0].rgb * P[2].z,
        # A (slot 0) at UV 16 * P[1].x, B (slot 1) at UV 20 * P[1].y, C (slot 3) at UV 16 * P[1].z; the lightmap at 24
        # (slot 4, the normal map, not used)
        z = params[2][2] if len(params) > 2 else 1.0
        return {'mode': 'blend3', 'src0': 16, 'src1': 20, 'mask': 20, 'lm': 24, 'vclr': False,
                'scale0': [params[1][0]] * 2, 'scale1': [params[1][1]] * 2, 'scale2': [params[1][2]] * 2,
                'tint0': [params[0][i] * z for i in range(3)], 'tint1': [1.0, 1.0, 1.0],
                'slots': [slots[0], slots[1], slots[2], slots[3]]}
    if OVLY.match(shader) and len(slots) >= 2 and min(slots[:2]) >= 0 and len(params) >= 2 and len(pairs) >= 2:
        # road_diff_spec_ovly_2 (AmalfiGP's cobbles; disassembled from the game's own ROAD_DIFF_SPEC_OVLY_2.fxobj,
        # tools/fm3_trackshader.py): an overlay blend, t0 (c120 = P[0]: UV0 * xy) and t1 (c121 = P[1]: the lightmap's UV
        # * xy): t1 < 0.5 ? 2 t0 t1 : 1 - 2 (1 - t0)(1 - t1); then x lerp(c247, c248, lightmap) as every lit surface
        return {'mode': 'ovly', 'src0': pairs[0], 'src1': pairs[1], 'mask': None, 'lm': pairs[1], 'vclr': False,
                'scale0': list(params[0][:2]), 'scale1': list(params[1][:2]), 'tint0': [1.0, 1.0, 1.0],
                'tint1': [1.0, 1.0, 1.0], 'slots': slots[:2]}
    if CURB.match(shader) and len(slots) >= 2 and min(slots[:2]) >= 0 and len(pairs) >= 2 and params:
        # shldr_road_blnd_spec_3 (curbs, painted run-off; captured, ps aa004de7): t0 at UV0 * lerp(P[0].rgb, 1, t1.g at
        # UV1); the lightmap on UV1
        return {'mode': 'curb', 'src0': pairs[0], 'src1': pairs[1], 'mask': None, 'lm': pairs[1], 'vclr': False,
                'scale0': [1.0, 1.0], 'scale1': [1.0, 1.0], 'tint0': list(params[0][:3]), 'tint1': [1.0, 1.0, 1.0],
                'slots': slots[:2]}
    if ROAD_DIFF.match(shader) and len(slots) >= 2 and min(slots[:2]) >= 0 and params:
        return {'mode': 'road', 'src0': 'xz', 'src1': 20 if stride >= 28 else pairs[0], 'mask': None, 'lm': None,
                'vclr': False, 'scale0': [params[0][0]] * 2, 'scale1': [1.0, 1.0], 'tint0': [1.0, 1.0, 1.0], 'tint1': [1.0, 1.0, 1.0],
                'slots': slots[:2]}
    if EDGE.match(shader) and len(slots) >= 4 and min(slots[:4]) >= 0 and len(params) >= 4 and len(pairs) >= 3:
        return {'mode': 'edge', 'src0': 'xz', 'src1': 16, 'mask': 20, 'lm': 24, 'vclr': False,
                'scale0': [params[0][0]] * 2, 'scale1': [1.0, 1.0], 'scale2': list(params[3][:2]),
                'tint0': [1.0, 1.0, 1.0], 'tint1': [1.0, 1.0, 1.0], 'slots': slots[:4]}
    if MIX.match(shader) and len(slots) >= 4 and min(slots[:4]) >= 0 and len(params) >= 4 and stride >= 28:
        # hw0/hw1 = base layer, hw2 = channel mask (red = second layer), hw3 = second layer at P[3].xy; UV0 at byte 20
        # (16 = vertex colour), mask and lightmap at 24 (0..1 per patch; the Ladera tree garden's islands)
        return {'mode': 'mix', 'src0': 20, 'src1': 20, 'mask': 24, 'lm': 24, 'vclr': False,
                'scale0': list(params[0][:2]), 'scale1': list(params[3][:2]), 'tint0': [1.0, 1.0, 1.0],
                'tint1': [1.0, 1.0, 1.0], 'slots': [slots[0], slots[3], slots[2]]}
    if shader == 'road_blnd_2' and len(slots) >= 2 and min(slots[:2]) >= 0 and len(params) >= 3:
        # (disassembled, ROAD_BLND_2.fxobj) grain g (slot 0) at world (x, z) * P[1].x, the value v (slot 1) at UV 16 *
        # P[1].yz: g * P[0] + v * (g + P[2] - g * P[0]) (CrownJewel: P[0] 0, P[2] 0.1; Motegi: 0.16, 0; before, the
        # captured-frame fit v * 0.34 * g / mean(g) for all, Motegi's road far too light)
        return {'mode': 'road1', 'src0': 'xz', 'src1': 16, 'mask': None, 'lm': None, 'vclr': False,
                'scale0': [params[1][0]] * 2, 'scale1': list(params[1][1:3]), 'tint0': list(params[0][:3]),
                'tint1': list(params[2][:3]), 'slots': slots[:2]}
    if PAINT.match(shader) and len(slots) >= 3 and min(slots[:3]) >= 0 and len(params) >= 5:
        # painted asphalt (kerb stripes, pit markings; SHLDR_4CLR_BLND_MASK_2.fxobj disassembled, 2026-11-26): the grain
        # g (slot 0) at world (x, z) * P[1].x; the paint mask (slot 1) at UV 16 * P[3].xy, its red channel (P[1].y == 0)
        # or green; the blend value v (slot 2, rgb) at the lightmap's UV * P[5].xy. g' = g + mask * P[2] (the paint is
        # added to the grain: the asphalt shows through it), colour = g' * P[0] + v * (g' + P[4] - g' * P[0]), x the
        # lightmap. (Until then a fitted flat paint colour over the mask's alpha: clean, too bright stripes.)
        return {'mode': 'paint4', 'src0': 'xz', 'src1': 16, 'mask': 'uv1', 'lm': None, 'vclr': False,
                'scale0': [params[1][0]] * 2, 'scale1': list(params[3][:2]),
                'scale2': list(params[5][:2]) if len(params) > 5 else [1.0, 1.0],
                'tint0': list(params[0][:3]), 'tint1': list(params[4][:3]), 'tint2': list(params[2][:3]),
                'chan': float(params[1][1]), 'slots': slots[:3]}
    if ROAD.match(shader) or PAINT.match(shader):
        if len(slots) < 2 or min(slots[:2]) < 0 or len(params) < 2:
            return None
        r = {'mode': 'road', 'src0': 'xz', 'src1': 16, 'mask': None, 'lm': None, 'vclr': False,
             'scale0': [params[1][0], params[1][0]], 'scale1': [1.0, 1.0], 'tint0': [1.0, 1.0, 1.0],
             'tint1': [1.0, 1.0, 1.0], 'slots': slots[:2]}
        if PAINT.match(shader) and len(params) > 2:
            c = [v * 0.75 for v in params[2][:3]]
            sat = (max(c) - min(c)) / max(max(c), 1e-6)
            r.update(mode='paint', tint1=[min(1.0, c[i] + SHEEN[i] * sat) for i in range(3)])
        return r
    return None
