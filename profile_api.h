/*
 * profile_api.h — host API for game profile code modules, v0.1 draft.
 *
 * Meaning: see PROFILES.md §8. A profile module is normally built for wasm32
 * (clang --target=wasm32 -nostdlib -Wl,--no-entry). The same source also builds as
 * a trusted native plugin, where the host provides these functions as exports.
 *
 * Conventions:
 *   - strings are (pointer, length) pairs, UTF-8, not NUL-terminated
 *   - functions returning int32_t return FIRP_OK (0) or a negative firp_status
 *   - guest addresses are always 64-bit (firp_gaddr), whatever the guest's pointer size
 */
#ifndef FIR_PROFILE_API_H
#define FIR_PROFILE_API_H

#include "frame_ir.h"

#ifdef __cplusplus
extern "C" {
#endif

#if defined(__wasm__)
#define FIRP_IMPORT(name) __attribute__((import_module("fir"), import_name(#name)))
#define FIRP_EXPORT(name) __attribute__((export_name(#name)))
#else
#define FIRP_IMPORT(name)
#define FIRP_EXPORT(name)
#endif

#define FIRP_API_VERSION 1

typedef uint64_t firp_gaddr;

enum firp_status {
    FIRP_OK               = 0,
    FIRP_ERR_UNMAPPED     = -1, /* guest address not mapped / null in a chain */
    FIRP_ERR_NOT_ALLOWED  = -2, /* write outside declared regions, undeclared patch, ... */
    FIRP_ERR_UNSUPPORTED  = -3, /* host lacks the capability */
    FIRP_ERR_BAD_ARG      = -4,
    FIRP_ERR_NOT_FOUND    = -5, /* unknown symbol / patch / probe id */
    FIRP_ERR_NOT_IN_HOOK  = -6  /* hook_* call outside a hook callback */
};

/* firp_host_capabilities() bits; see PROFILES.md §7 */
enum {
    FIRP_CAP_MEM_READ       = 1u << 0,
    FIRP_CAP_MEM_WRITE      = 1u << 1,
    FIRP_CAP_HOOK_ENTRY     = 1u << 2,
    FIRP_CAP_HOOK_EXIT      = 1u << 3,
    FIRP_CAP_HOOK_REPLACE   = 1u << 4,
    FIRP_CAP_HOOK_HOT       = 1u << 5,
    FIRP_CAP_SIGNATURE_SCAN = 1u << 6,
    FIRP_CAP_CALL_GUEST     = 1u << 7,
    FIRP_CAP_INPUT_REPLAY   = 1u << 8
};

enum firp_hook_kind { FIRP_HOOK_ENTRY = 0, FIRP_HOOK_EXIT = 1, FIRP_HOOK_REPLACE = 2 };

enum firp_log_level { FIRP_LOG_DEBUG = 0, FIRP_LOG_INFO, FIRP_LOG_WARN, FIRP_LOG_ERROR };

enum firp_config_type { FIRP_CFG_BOOL = 0, FIRP_CFG_I64, FIRP_CFG_F64, FIRP_CFG_STRING };

/* ------------------------------------------------------------------------- */
/* Host info                                                                 */
/* ------------------------------------------------------------------------- */

FIRP_IMPORT(api_version)       uint32_t firp_api_version(void);
FIRP_IMPORT(host_capabilities) uint32_t firp_host_capabilities(void);
FIRP_IMPORT(platform)          uint32_t firp_platform(void);       /* fir_platform */
FIRP_IMPORT(guest_big_endian)  uint32_t firp_guest_big_endian(void);

/* Resolve a symbol from builds.toml for the active build. */
FIRP_IMPORT(symbol) int32_t firp_symbol(const char *name, uint32_t name_len, firp_gaddr *out);

/* ------------------------------------------------------------------------- */
/* Guest memory                                                              */
/* ------------------------------------------------------------------------- */

/* Raw bytes, no endian conversion. Never faults: unmapped ranges return FIRP_ERR_UNMAPPED. */
FIRP_IMPORT(mem_read)  int32_t firp_mem_read(firp_gaddr addr, void *dst, uint32_t size);

/* Only inside [[region]] entries declared writable in the profile. */
FIRP_IMPORT(mem_write) int32_t firp_mem_write(firp_gaddr addr, const void *src, uint32_t size);

/* Enable/disable a patch declared in hooks.toml. */
FIRP_IMPORT(patch_set) int32_t firp_patch_set(const char *id, uint32_t id_len, int32_t enabled);

/* ------------------------------------------------------------------------- */
/* Hooks                                                                     */
/* ------------------------------------------------------------------------- */

/* Register a hook at runtime (declared hooks in hooks.toml are installed by the host).
 * The callback arrives as fir_on_hook(callback_id). */
FIRP_IMPORT(hook_add)    int32_t firp_hook_add(firp_gaddr at, uint32_t kind, uint32_t callback_id);
FIRP_IMPORT(hook_remove) int32_t firp_hook_remove(firp_gaddr at, uint32_t callback_id);

/* Inside a hook callback. Arguments follow the guest ABI's integer / float argument
 * registers (PPC r3.., f1..; MIPS a0..; x86 stack slots for cdecl/stdcall/thiscall). */
FIRP_IMPORT(hook_arg)      uint64_t firp_hook_arg(uint32_t index);
FIRP_IMPORT(hook_arg_f64)  double   firp_hook_arg_f64(uint32_t index);
FIRP_IMPORT(hook_ret)      uint64_t firp_hook_ret(void);           /* exit hooks */
FIRP_IMPORT(hook_set_ret)  int32_t  firp_hook_set_ret(uint64_t value); /* replace hooks */
FIRP_IMPORT(hook_call_original) int32_t firp_hook_call_original(void); /* replace hooks */

/* Call a guest function (FIRP_CAP_CALL_GUEST). */
FIRP_IMPORT(call_guest) int32_t firp_call_guest(firp_gaddr fn, const uint64_t *args,
                                                uint32_t arg_count, uint64_t *ret);

/* ------------------------------------------------------------------------- */
/* Probes and emitting                                                       */
/* ------------------------------------------------------------------------- */

/* Run a probe declared in probes.toml right now (its records are emitted as usual). */
FIRP_IMPORT(probe_run) int32_t firp_probe_run(const char *id, uint32_t id_len);

/* Emit one semantic Frame IR record: CAMERA, OBJECT, ENVIRONMENT, LIGHT, EVENT or
 * ANNOTATE. `record` is the full fir_* struct with h.type set; the host fills h.size
 * and, if params_size > 0, the record's `params` blob ref. Other record types are
 * rejected with FIRP_ERR_NOT_ALLOWED. */
FIRP_IMPORT(emit) int32_t firp_emit(const void *record, uint32_t record_size,
                                    const void *params, uint32_t params_size);

/* ------------------------------------------------------------------------- */
/* Time, config, logging                                                     */
/* ------------------------------------------------------------------------- */

FIRP_IMPORT(frame_index) uint64_t firp_frame_index(void);
FIRP_IMPORT(sim_time)    double   firp_sim_time(void);   /* current sample time */
FIRP_IMPORT(set_sim_time) int32_t firp_set_sim_time(double t); /* for hooks that own the sim clock */

/* Read a value from the merged profile + user config ([config] tables). */
FIRP_IMPORT(config_get) int32_t firp_config_get(const char *key, uint32_t key_len,
                                                uint32_t type, void *out, uint32_t out_size);

FIRP_IMPORT(log) void firp_log(uint32_t level, const char *msg, uint32_t msg_len);

/* ------------------------------------------------------------------------- */
/* Exports a module may implement (all optional)                             */
/* ------------------------------------------------------------------------- */

int32_t fir_profile_load(uint32_t build_index);
void    fir_on_frame_begin(uint64_t frame_index);
void    fir_on_frame_end(uint64_t frame_index);
void    fir_on_hook(uint32_t callback_id);
void    fir_on_capture(uint32_t mode);           /* FIR_CAPTURE_* bits, 0 = stopped */
void    fir_on_unload(void);

/* ------------------------------------------------------------------------- */
/* Inline helpers (no host calls beyond mem_read)                            */
/* ------------------------------------------------------------------------- */

static inline uint32_t firp_bswap32(uint32_t v) {
    return (v >> 24) | ((v >> 8) & 0xFF00u) | ((v << 8) & 0xFF0000u) | (v << 24);
}

static inline uint64_t firp_bswap64(uint64_t v) {
    return ((uint64_t)firp_bswap32((uint32_t)v) << 32) | firp_bswap32((uint32_t)(v >> 32));
}

/* Read a u32 in the guest's native byte order. */
static inline int32_t firp_read_u32(firp_gaddr addr, uint32_t *out) {
    uint32_t v;
    int32_t r = firp_mem_read(addr, &v, 4);
    if (r != FIRP_OK) return r;
    *out = firp_guest_big_endian() ? firp_bswap32(v) : v;
    return FIRP_OK;
}

static inline int32_t firp_read_f32(firp_gaddr addr, float *out) {
    uint32_t bits;
    int32_t r = firp_read_u32(addr, &bits);
    if (r != FIRP_OK) return r;
    union { uint32_t u; float f; } c;
    c.u = bits;
    *out = c.f;
    return FIRP_OK;
}

/* Read a 32-bit guest pointer (X360/PS3/PS2/PS1/Xbox/32-bit PC). */
static inline int32_t firp_read_ptr32(firp_gaddr addr, firp_gaddr *out) {
    uint32_t v;
    int32_t r = firp_read_u32(addr, &v);
    if (r != FIRP_OK) return r;
    if (v == 0) return FIRP_ERR_UNMAPPED;
    *out = v;
    return FIRP_OK;
}

/* Read `count` consecutive f32 values in guest byte order. */
static inline int32_t firp_read_f32s(firp_gaddr addr, float *out, uint32_t count) {
    for (uint32_t i = 0; i < count; ++i) {
        int32_t r = firp_read_f32(addr + 4u * i, &out[i]);
        if (r != FIRP_OK) return r;
    }
    return FIRP_OK;
}

/* Emit helpers: set the record type and forward to firp_emit. */
static inline int32_t firp_emit_camera(fir_camera *c) {
    c->h.type = FIR_REC_CAMERA; c->h.flags = 0;
    return firp_emit(c, (uint32_t)sizeof *c, 0, 0);
}
static inline int32_t firp_emit_object(fir_object *o, const void *params, uint32_t params_size) {
    o->h.type = FIR_REC_OBJECT; o->h.flags = 0;
    return firp_emit(o, (uint32_t)sizeof *o, params, params_size);
}
static inline int32_t firp_emit_event(fir_event *e, const void *params, uint32_t params_size) {
    e->h.type = FIR_REC_EVENT; e->h.flags = 0;
    return firp_emit(e, (uint32_t)sizeof *e, params, params_size);
}
static inline int32_t firp_emit_annotate(fir_annotate *a) {
    a->h.type = FIR_REC_ANNOTATE; a->h.flags = 0;
    return firp_emit(a, (uint32_t)sizeof *a, 0, 0);
}

#define FIRP_STR(s) (s), (uint32_t)(sizeof(s) - 1) /* string literal → (ptr, len) */

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* FIR_PROFILE_API_H */
