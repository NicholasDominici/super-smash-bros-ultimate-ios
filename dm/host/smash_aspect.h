// Exact Smash13.0.5 logical4:3 UI projection/clipping admission and diagnostics.
#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint64_t projections, perspective_projections, draws, rejected;
    int installed;
} dm_smash_aspect_stats;
// Main must already be relocated from a completely prepared private4:3 cache.
void dm_smash_aspect_install(void);
void dm_smash_aspect_get_stats(dm_smash_aspect_stats *out);
#ifdef __cplusplus
}
#endif
