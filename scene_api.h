/*
 * scene_api.h — Scene API v0.1 draft: the interface a renderer backend implements.
 *
 * Meaning: see SCENE_API.md. In-process C interface (core and renderer share a
 * process), so unlike frame_ir.h these structs are not a wire format.
 *
 * Handles are allocated by the core (non-zero, unique per object type), so calls can
 * be queued by the backend without round trips. Every create/update/destroy call must
 * happen between begin_update and end_update; apply-time is end_update.
 */
#ifndef SCENE_API_H
#define SCENE_API_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define SCN_API_VERSION 1

typedef uint32_t scn_texture;
typedef uint32_t scn_mesh;
typedef uint32_t scn_material;
typedef uint32_t scn_instance;
typedef uint32_t scn_light;
typedef uint32_t scn_probe;
typedef uint32_t scn_effect;
typedef uint32_t scn_view;
typedef uint32_t scn_layer;
typedef uint32_t scn_lighting_set;

typedef struct scn_vec2 { float x, y; } scn_vec2;
typedef struct scn_vec3 { float x, y, z; } scn_vec3;
typedef struct scn_vec4 { float x, y, z, w; } scn_vec4;
/* Same convention as Frame IR: column vectors, row-major storage, top 3 rows. */
typedef struct scn_mat3x4 { float m[3][4]; } scn_mat3x4;
typedef struct scn_mat4   { float m[4][4]; } scn_mat4;

typedef struct scn_hash128 { uint64_t lo, hi; } scn_hash128; /* asset DB ids */

typedef enum scn_result {
    SCN_OK = 0, SCN_ERR_UNSUPPORTED = -1, SCN_ERR_BAD_HANDLE = -2,
    SCN_ERR_BAD_ARG = -3, SCN_ERR_OUT_OF_MEMORY = -4, SCN_ERR_DEVICE_LOST = -5
} scn_result;

/* ------------------------------------------------------------------------- */
/* Textures                                                                  */
/* ------------------------------------------------------------------------- */

typedef enum scn_format {
    SCN_FMT_RGBA8_UNORM = 0, SCN_FMT_RGBA8_SRGB, SCN_FMT_RGBA16F,
    SCN_FMT_BC1_SRGB, SCN_FMT_BC3_SRGB, SCN_FMT_BC4, SCN_FMT_BC5,
    SCN_FMT_BC6H, SCN_FMT_BC7_UNORM, SCN_FMT_BC7_SRGB
} scn_format;

typedef enum scn_texture_kind { SCN_TEX_2D = 0, SCN_TEX_CUBE, SCN_TEX_2D_ARRAY, SCN_TEX_3D } scn_texture_kind;

typedef struct scn_texture_desc {
    scn_texture_kind kind;
    scn_format format;
    uint32_t width, height, depth_or_layers;
    uint32_t mip_count;
    const void *data;       /* all mips/layers, tightly packed; NULL for shared/RTT */
    size_t data_size;
    scn_hash128 asset_id;   /* for debug views and caching; zero if not from the DB */
} scn_texture_desc;

typedef struct scn_shared_image_desc {
    uint64_t os_handle;     /* Win32 HANDLE / fd of exported GPU memory */
    scn_format format;
    uint32_t width, height;
} scn_shared_image_desc;

/* ------------------------------------------------------------------------- */
/* Meshes                                                                    */
/* ------------------------------------------------------------------------- */

/* Canonical vertex layout produced by the asset pipeline (fixed, interleaved). */
typedef struct scn_vertex {
    scn_vec3 position;
    scn_vec3 normal;
    scn_vec4 tangent;       /* w = bitangent sign */
    scn_vec2 uv0;
    scn_vec2 uv1;           /* lightmap UVs; zero if none */
    uint32_t color;         /* RGBA8, original vertex color */
    uint32_t _pad;
} scn_vertex;

typedef struct scn_skin_vertex {
    uint8_t  joints[4];
    uint8_t  weights[4];    /* unorm, sum 255 */
} scn_skin_vertex;

typedef struct scn_submesh {
    uint32_t first_index, index_count;
    scn_material material;  /* default; instances may override */
} scn_submesh;

typedef struct scn_mesh_lod {
    float    screen_size;   /* switch below this projected size (0..1 of view height) */
    uint32_t first_submesh, submesh_count;
} scn_mesh_lod;

typedef struct scn_mesh_desc {
    const scn_vertex *vertices;   uint32_t vertex_count;
    const scn_skin_vertex *skin;  /* NULL or vertex_count entries */
    const uint32_t *indices;      uint32_t index_count; /* triangle list */
    const scn_submesh *submeshes; uint32_t submesh_count;
    const scn_mesh_lod *lods;     uint32_t lod_count;   /* 0 = single LOD */
    const scn_vec3 *morph_deltas; uint32_t morph_count; /* morph_count * vertex_count position deltas */
    scn_vec3 bounds_min, bounds_max;
    scn_hash128 asset_id;
} scn_mesh_desc;

/* ------------------------------------------------------------------------- */
/* Materials                                                                 */
/* ------------------------------------------------------------------------- */

typedef enum scn_archetype {
    SCN_ARCH_LEGACY = 0, SCN_ARCH_UNLIT, SCN_ARCH_STANDARD, SCN_ARCH_CAR_PAINT,
    SCN_ARCH_GLASS, SCN_ARCH_FOLIAGE, SCN_ARCH_SKIN, SCN_ARCH_WATER, SCN_ARCH_TERRAIN,
    SCN_ARCH_DECAL, SCN_ARCH_EMISSIVE, SCN_ARCH_PARTICLE, SCN_ARCH_SKY, SCN_ARCH_EXTENSION,
    SCN_ARCH_COUNT
} scn_archetype;

typedef enum scn_alpha_mode { SCN_ALPHA_OPAQUE = 0, SCN_ALPHA_CUTOUT, SCN_ALPHA_BLEND,
                              SCN_ALPHA_ADDITIVE, SCN_ALPHA_PREMULTIPLIED } scn_alpha_mode;
typedef enum scn_cull { SCN_CULL_BACK = 0, SCN_CULL_FRONT, SCN_CULL_NONE } scn_cull;
typedef enum scn_vertex_color_mode { SCN_VCOL_IGNORE = 0, SCN_VCOL_MULTIPLY_ALBEDO,
                                     SCN_VCOL_AMBIENT_OCCLUSION, SCN_VCOL_BAKED_LIGHT } scn_vertex_color_mode;

typedef enum scn_texture_role {
    SCN_ROLE_ALBEDO = 0, SCN_ROLE_NORMAL, SCN_ROLE_ORM, SCN_ROLE_EMISSIVE, SCN_ROLE_DETAIL,
    SCN_ROLE_MASK, SCN_ROLE_ENV_HINT,
    SCN_ROLE_ALBEDO1, SCN_ROLE_ALBEDO2, SCN_ROLE_ALBEDO3,
    SCN_ROLE_NORMAL1, SCN_ROLE_NORMAL2, SCN_ROLE_NORMAL3,
    SCN_ROLE_COUNT
} scn_texture_role;

typedef struct scn_uv_transform {
    scn_vec2 scale, offset;
    float    rotation;      /* radians */
    scn_vec2 scroll;        /* UV units per second (animated textures) */
} scn_uv_transform;

/* Superset parameter block; each archetype reads the fields listed in SCENE_API.md §5. */
typedef struct scn_material_params {
    scn_vec4 base_color;          /* linear rgb + alpha */
    float    metallic, roughness, normal_scale, occlusion_strength;
    scn_vec3 emissive;            float emissive_strength;
    float    alpha_cutoff;
    /* car_paint */
    float    clearcoat, clearcoat_roughness, flake_density, flake_scale;
    scn_vec3 flake_color;
    /* glass / water */
    float    transmission, ior, depth_fog, wave_scale;
    scn_vec2 flow;
    /* foliage / skin */
    float    translucency, wind_strength;
    scn_vec3 subsurface_color;    float subsurface_radius;
    /* terrain: per-layer tint and roughness */
    scn_vec4 layer_color[4];
    float    layer_roughness[4];
    /* particle */
    float    soft_distance;       uint32_t lit;
} scn_material_params;

typedef struct scn_material_desc {
    scn_archetype archetype;
    scn_alpha_mode alpha_mode;
    scn_cull cull;
    scn_vertex_color_mode vertex_color_mode;
    scn_material_params params;
    scn_uv_transform uv;
    scn_texture textures[SCN_ROLE_COUNT];  /* 0 = unused */
    /* SCN_ARCH_EXTENSION: compiled shader + parameter blob (PROFILES.md §11) */
    scn_hash128 extension_id;
    const void *extension_params; size_t extension_params_size;
    scn_hash128 source_state_hash;          /* original state, for debug views */
} scn_material_desc;

/* ------------------------------------------------------------------------- */
/* Instances                                                                 */
/* ------------------------------------------------------------------------- */

enum {
    SCN_INST_STATIC        = 1u << 0, /* never moves; backend may bake into BVH / batches */
    SCN_INST_CAST_SHADOW   = 1u << 1,
    SCN_INST_VISIBLE       = 1u << 2,
    SCN_INST_USE_LIGHTMAP  = 1u << 3, /* static: uses the lighting set's lightmap */
    SCN_INST_NO_MOTION_VEC = 1u << 4  /* teleported this frame: no motion vectors */
};

typedef enum scn_category {  /* mirrors fir_category, for debug views and per-view filters */
    SCN_CAT_UNKNOWN = 0, SCN_CAT_WORLD_STATIC, SCN_CAT_WORLD_DYNAMIC, SCN_CAT_CHARACTER,
    SCN_CAT_VEHICLE, SCN_CAT_SKY, SCN_CAT_WATER, SCN_CAT_FOLIAGE, SCN_CAT_PARTICLE,
    SCN_CAT_DECAL
} scn_category;

typedef struct scn_instance_desc {
    scn_mesh mesh;
    scn_mat3x4 transform;          /* object -> world at render time */
    uint32_t flags;                /* SCN_INST_* */
    scn_category category;
    uint32_t layer_mask;           /* which views see it (bit per view group) */
    uint32_t lightmap_index;       /* into the active lighting set */
    scn_vec4 lightmap_scale_offset;
    uint64_t instance_key;         /* Frame IR instance key, for debug views */
} scn_instance_desc;

/* ------------------------------------------------------------------------- */
/* Lights, environment, probes                                               */
/* ------------------------------------------------------------------------- */

typedef enum scn_light_type { SCN_LIGHT_DIRECTIONAL = 0, SCN_LIGHT_POINT, SCN_LIGHT_SPOT,
                              SCN_LIGHT_AREA_RECT } scn_light_type;

typedef struct scn_light_desc {
    scn_light_type type;
    scn_mat3x4 transform;          /* position + orientation (-Z = direction) */
    scn_vec3 color;                float intensity; /* lux (directional) or lumens */
    float    range;
    float    spot_inner, spot_outer;
    scn_vec2 area_size;
    uint32_t cast_shadow;
    uint32_t baked_only;           /* contributes to bakes only, not drawn dynamically */
} scn_light_desc;

typedef struct scn_lighting_set_desc {
    const char *path;              /* local bake output (lightmaps + probes) */
    float time_of_day_hours;       /* the variant this set was baked for; <0 = any */
} scn_lighting_set_desc;

typedef struct scn_environment_desc {
    scn_lighting_set lighting_sets[2]; /* blended by lighting_blend (time of day) */
    float    lighting_blend;
    scn_texture sky;               /* 0 = procedural atmosphere */
    scn_vec3 sun_direction;        /* toward the sun */
    scn_vec3 sun_color;            float sun_intensity;
    scn_vec3 ambient_color;
    scn_vec3 fog_color;            float fog_density, fog_start, fog_height_falloff;
    float    exposure_ev;          uint32_t auto_exposure;
    float    wetness;              /* 0..1, drives water/puddle materials */
} scn_environment_desc;

typedef enum scn_probe_type { SCN_PROBE_REFLECTION = 0, SCN_PROBE_IRRADIANCE_VOLUME } scn_probe_type;

typedef struct scn_probe_desc {
    scn_probe_type type;
    scn_vec3 position;
    scn_vec3 extents;              /* box influence (reflection) or volume size */
    uint32_t realtime;             /* re-render at runtime (e.g. follows a car) */
    scn_instance follow;           /* realtime probes may follow an instance */
} scn_probe_desc;

/* ------------------------------------------------------------------------- */
/* Effects                                                                   */
/* ------------------------------------------------------------------------- */

typedef enum scn_effect_type { SCN_FX_SMOKE = 0, SCN_FX_DUST, SCN_FX_SPARKS, SCN_FX_SPLASH,
                               SCN_FX_DEBRIS, SCN_FX_FIRE, SCN_FX_SKID, SCN_FX_EXTENSION } scn_effect_type;

typedef struct scn_effect_desc {
    scn_effect_type type;
    scn_hash128 extension_id;      /* SCN_FX_EXTENSION */
    scn_vec3 position, direction;
    scn_vec3 color;                float intensity;
    float    duration;             /* seconds; 0 = until destroyed */
    scn_instance attach;           /* follow this instance (local offset = position) */
} scn_effect_desc;

/* ------------------------------------------------------------------------- */
/* Views and layers                                                          */
/* ------------------------------------------------------------------------- */

typedef enum scn_upscaler { SCN_UPSCALE_NONE = 0, SCN_UPSCALE_TAA, SCN_UPSCALE_FSR,
                            SCN_UPSCALE_DLSS, SCN_UPSCALE_XESS } scn_upscaler;

typedef struct scn_view_desc {
    scn_mat3x4 camera_to_world;
    scn_mat4   projection;         /* off-axis allowed; canonical NDC (Frame IR §4) */
    scn_mat3x4 prev_camera_to_world; /* for motion vectors */
    scn_mat4   prev_projection;
    /* target: the output surface region, or an RTT texture */
    uint32_t output_index;         /* which window/surface; ignored for RTT */
    int32_t  viewport[4];          /* x, y, w, h in output pixels */
    scn_texture rtt_target;        /* non-zero = render to this texture */
    /* settings */
    float    resolution_scale;     /* render res / output res before upscaling */
    scn_upscaler upscaler;
    float    shadow_distance;
    float    lod_bias;
    uint32_t layer_mask;           /* instances visible in this view */
    uint32_t multiview_group;      /* views with equal non-zero groups may share a pass */
    uint32_t priority;             /* draw order for RTT dependencies (lower first) */
} scn_view_desc;

typedef enum scn_layer_kind { SCN_LAYER_HUD = 0, SCN_LAYER_UNCLAIMED_WORLD, SCN_LAYER_FULL_FRAME } scn_layer_kind;

typedef struct scn_layer_desc {
    scn_layer_kind kind;
    scn_texture color;             /* usually a shared image */
    scn_texture depth;             /* optional, UNCLAIMED_WORLD depth test */
    uint32_t view_mask;            /* bit per view index */
    scn_vec4 dest_rect;            /* normalized placement within each view */
    uint64_t wait_semaphore_os_handle;
    uint64_t wait_value;
} scn_layer_desc;

/* ------------------------------------------------------------------------- */
/* Frames, debug, stats                                                      */
/* ------------------------------------------------------------------------- */

typedef enum scn_debug_mode {
    SCN_DEBUG_NONE = 0, SCN_DEBUG_ORIGINAL_ONLY, SCN_DEBUG_SPLIT_AB, SCN_DEBUG_CATEGORY,
    SCN_DEBUG_ARCHETYPE, SCN_DEBUG_ASSET_ID, SCN_DEBUG_LIGHTMAP, SCN_DEBUG_PROBES,
    SCN_DEBUG_WIREFRAME, SCN_DEBUG_OVERDRAW
} scn_debug_mode;

typedef struct scn_frame {
    uint64_t frame_index;
    double   render_time;          /* sim-clock time this frame represents */
    float    delta_seconds;        /* since previous render frame (effects, scroll) */
    scn_debug_mode debug_mode;
} scn_frame;

typedef struct scn_stats {
    double   cpu_ms, gpu_ms;
    uint32_t draws, instances_visible, triangles;
    scn_vec2 jitter[8];            /* per view, as applied by the upscaler */
} scn_stats;

typedef struct scn_backend_info {
    const char *name;
    uint32_t api_version;          /* SCN_API_VERSION the backend was built against */
    uint32_t supports_multiview;
    uint32_t supports_shared_images;
    uint32_t supported_upscalers;  /* bit per scn_upscaler */
    uint32_t max_views;
} scn_backend_info;

/* ------------------------------------------------------------------------- */
/* Backend interface                                                         */
/* ------------------------------------------------------------------------- */

typedef struct scn_backend scn_backend;

typedef struct scn_backend_vtbl {
    void       (*info)(scn_backend *, scn_backend_info *out);

    scn_result (*begin_update)(scn_backend *);
    scn_result (*end_update)(scn_backend *);   /* changes take effect here */

    scn_result (*texture_create)(scn_backend *, scn_texture, const scn_texture_desc *);
    scn_result (*texture_create_shared)(scn_backend *, scn_texture, const scn_shared_image_desc *);
    scn_result (*mesh_create)(scn_backend *, scn_mesh, const scn_mesh_desc *);
    scn_result (*material_create)(scn_backend *, scn_material, const scn_material_desc *);
    scn_result (*material_update)(scn_backend *, scn_material, const scn_material_desc *);

    scn_result (*instance_create)(scn_backend *, scn_instance, const scn_instance_desc *);
    scn_result (*instance_set_transform)(scn_backend *, scn_instance,
                                         const scn_mat3x4 *current, const scn_mat3x4 *previous);
    scn_result (*instance_set_flags)(scn_backend *, scn_instance, uint32_t flags);
    scn_result (*instance_set_material)(scn_backend *, scn_instance, uint32_t submesh, scn_material);
    scn_result (*instance_set_skin)(scn_backend *, scn_instance, const scn_mat3x4 *bones,
                                    const scn_mat3x4 *prev_bones, uint32_t bone_count);
    scn_result (*instance_set_morphs)(scn_backend *, scn_instance, const float *weights, uint32_t count);
    scn_result (*instance_set_extension_deform)(scn_backend *, scn_instance, scn_hash128 extension_id,
                                                const void *params, size_t params_size);

    scn_result (*light_create)(scn_backend *, scn_light, const scn_light_desc *);
    scn_result (*light_update)(scn_backend *, scn_light, const scn_light_desc *);
    scn_result (*lighting_set_create)(scn_backend *, scn_lighting_set, const scn_lighting_set_desc *);
    scn_result (*probe_create)(scn_backend *, scn_probe, const scn_probe_desc *);
    scn_result (*environment_set)(scn_backend *, const scn_environment_desc *);

    scn_result (*effect_spawn)(scn_backend *, scn_effect, const scn_effect_desc *);
    scn_result (*effect_update)(scn_backend *, scn_effect, const scn_effect_desc *);

    scn_result (*view_create)(scn_backend *, scn_view, const scn_view_desc *);
    scn_result (*view_update)(scn_backend *, scn_view, const scn_view_desc *);
    scn_result (*layer_create)(scn_backend *, scn_layer, const scn_layer_desc *);
    scn_result (*layer_update)(scn_backend *, scn_layer, const scn_layer_desc *);

    /* one destroy for every object type */
    scn_result (*destroy)(scn_backend *, uint32_t object_type, uint32_t handle);

    scn_result (*render)(scn_backend *, const scn_frame *);
    void       (*stats)(scn_backend *, scn_stats *out);
    /* extension shaders compiled at install time (PROFILES.md §11) */
    scn_result (*extension_register)(scn_backend *, scn_hash128 id, const void *spirv, size_t size);
} scn_backend_vtbl;

struct scn_backend {
    const scn_backend_vtbl *vtbl;
    void *impl;
};

typedef enum scn_object_type {
    SCN_OBJ_TEXTURE = 0, SCN_OBJ_MESH, SCN_OBJ_MATERIAL, SCN_OBJ_INSTANCE, SCN_OBJ_LIGHT,
    SCN_OBJ_PROBE, SCN_OBJ_EFFECT, SCN_OBJ_VIEW, SCN_OBJ_LAYER, SCN_OBJ_LIGHTING_SET
} scn_object_type;

/* Backends are shared libraries exporting this entry point. */
typedef scn_result (*scn_create_backend_fn)(uint32_t api_version, const char *config_json,
                                            scn_backend **out);
#define SCN_CREATE_BACKEND_SYMBOL "scn_create_backend"

#ifdef __cplusplus
} /* extern "C" */
#endif

#endif /* SCENE_API_H */
