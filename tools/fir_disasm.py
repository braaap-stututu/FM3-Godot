#!/usr/bin/env python3
"""fir_disasm.py: disassemble a captured vertex shader (control flow, fetches, ALU) in fir_xenos' decoding.

    python -I fir_disasm.py capture.fir <vs hash hex>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fir_frame import load_vs_code  # noqa: E402
from fir_xenos import VECTOR_OPS, bits, decode_alu, parse  # noqa: E402

SCALAR_OPS = ("adds adds_prev muls muls_prev muls_prev2 maxs mins seqs sgts sges snes frcs truncs floors exp logc log rcpc rcpf "
              "rcp rsqc rsqf rsq maxas maxasf subs subs_prev setp_eq setp_ne setp_gt setp_ge setp_inv setp_pop setp_clr setp_rstr "
              "kills_eq kills_gt kills_ge kills_ne kills_one sqrt ?41 mulsc0 mulsc1 addsc0 addsc1 subsc0 subsc1 sin cos "
              "retain_prev").split()
CF_NAMES = ["nop", "exec", "exece", "cexec", "cexece", "cexec_pred", "cexece_pred", "loop_start", "loop_end", "ccall", "ret",
            "cjmp", "alloc", "cexec_pred_clean", "cexece_pred_clean", "vfetch_end"]


def src_text(s):
    rel = '[a0]' if s['rel'] == 1 else '[aL]' if s['rel'] == 2 else ''
    return ('-' if s['neg'] else '') + ('c' if s['const'] else 'r') + str(s['reg']) + rel + '.' + ''.join('xyzw'[q] for q in s['swz']) + \
        ('|abs|' if s['abs'] else '')


def disasm(code_words):
    words, cfs = parse(code_words, full=True)
    out = []
    for ci, (lo, hi) in enumerate(cfs):
        op = (hi >> 12) & 15
        if op in (7, 8, 9, 11):
            out.append(f'cf{ci} {CF_NAMES[op]} target {lo & 0x1FFF} uncond {(lo >> 13) & 1} pred {(lo >> 14) & 1} '
                       f'bool {(hi >> 2) & 0xFF} cond {(hi >> 10) & 1}')
            continue
        if op not in (1, 2, 3, 4, 5, 6, 13, 14):
            out.append(f'cf{ci} {CF_NAMES[op]}')
            continue
        addr, count, seq = lo & 0xFFF, (lo >> 12) & 7, (lo >> 16) & 0xFFF
        head = f'cf{ci} {CF_NAMES[op]}' + (f' bool {(hi >> 2) & 0xFF} cond {(hi >> 10) & 1}' if op in (3, 4, 13, 14) else
                                           f' pred cond {(hi >> 10) & 1}' if op in (5, 6) else '')
        out.append(head)
        for k in range(count):
            i = addr + k
            w = words[i * 3:i * 3 + 3]
            if (seq >> (2 * k)) & 1:
                out.append(f'  {i:3d} vfetch r{bits(w[0], 12, 6)}.{bits(w[1], 0, 12):03x} <- r{bits(w[0], 5, 6)}.{"xyzw"[bits(w[0], 30, 2)]} '
                           f'const {bits(w[0], 20, 5) * 3 + bits(w[0], 25, 2)} fmt {bits(w[1], 16, 6)} stride {bits(w[2], 0, 8)} '
                           f'off {bits(w[2], 8, 23)}{" mini" if bits(w[1], 30, 1) else ""}{" signed" if bits(w[1], 12, 1) else ""}'
                           f'{" norm" if not bits(w[1], 13, 1) else ""} exp {(bits(w[1], 24, 6) ^ 32) - 32}')
                continue
            a = decode_alu(w)
            sd = a['vdest'] if a['export'] else a['sdest']
            out.append(f"  {i:3d} {'(p' + str(int(a['pred_cond'])) + ') ' if a['pred'] else ''}{VECTOR_OPS[a['vop']]} "
                       f"{'e' if a['export'] else 'r'}{a['vdest']}.{a['vmask']:x} = {src_text(a['src'][0])}, {src_text(a['src'][1])}, "
                       f"{src_text(a['src'][2])} | {SCALAR_OPS[a['sop']] if a['sop'] < len(SCALAR_OPS) else a['sop']} "
                       f"{'e' if a['export'] else 'r'}{sd}.{a['smask']:x}")
    return out


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    code = load_vs_code(sys.argv[1])
    print('\n'.join(disasm(code[int(sys.argv[2], 16)])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
