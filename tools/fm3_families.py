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
        k = next((i for i, p in enumerate(params) if 0.05 <= p[2] <= 1.0 and p[3] >= 5), None)
        if k is None:
            return None
        return {'mode': 'blend', 'src0': pairs[0], 'src1': pairs[1] if len(pairs) >= 3 else pairs[0],
                'mask': pairs[-1], 'lm': pairs[-1], 'vclr': vclr and stride == 32,
                'scale0': list(params[k][:2]), 'scale1': list(params[k + 1][:2]) if k + 1 < len(params) else [1.0, 1.0],
                'tint0': list(params[0][:3]) if k > 0 else [1.0, 1.0, 1.0],
                'tint1': list(params[k + 2][:3]) if (vclr and k + 2 < len(params)) else [1.0, 1.0, 1.0],
                'slots': slots[:3]}
    pairs = list(range(16, stride - 3, 4))
    if REFL.match(shader) and slots and slots[0] >= 0 and params and pairs:
        # windows and glazing (diff_spec_refl_norm_4 / diff_spec_refl_3; captured ps f4e339d2): base t0 at UV0 * P[0].yz,
        # lightmap as usual, plus an environment cube reflection scaled by t0.a * P[0].x
        return {'mode': 'refl', 'src0': pairs[0], 'src1': pairs[0], 'mask': None, 'lm': None, 'vclr': False,
                'scale0': list(params[0][1:3]), 'scale1': [1.0, 1.0], 'tint0': [params[0][0]] * 3,
                'tint1': list(params[2][:3]) if len(params) > 2 else [1.0, 1.0, 1.0],  # reflection tint (teal glass)
                'slots': [slots[0], slots[0]]}
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
