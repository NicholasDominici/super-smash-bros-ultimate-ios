// Verified Smash 13.0.5 guard state accents; authored rumble stays independent.
#pragma once
#include <stdint.h>
#include <math.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct {
    uint64_t epoch, impact_sequence, impact_ns;
    unsigned hold_mask, impact_mask; // bit0 left trigger, bit1 right trigger
} dm_smash_feedback_output;
typedef struct {
    uint64_t mappings, transitions, heartbeats, impacts[8];
    int installed;
} dm_smash_feedback_stats;
// Shared safety policy, also used by the physical adapter. A side must be both
// game-confirmed and actually held; nonfinite framework samples stay neutral.
static inline unsigned dm_smash_feedback_trigger_mode(dm_smash_feedback_output value, int side, float travel) {
    if (side < 0 || side > 1 || !value.epoch || !isfinite(travel) || travel < .10f || travel > 1.f) return 0;
    unsigned bit = 1u << side;
    return !(value.hold_mask & bit) ? 0u : value.impact_mask & bit ? 2u : 1u;
}
// After main relocation, before guest execution; unsupported builds fail closed.
void dm_smash_feedback_install(void);
// Physical player slot. No guest pointer is retained or dereferenced by polling.
void dm_smash_feedback_poll(unsigned player, uint64_t now_ns, dm_smash_feedback_output *out);
void dm_smash_feedback_get_stats(dm_smash_feedback_stats *out);
#ifdef __cplusplus
}
#endif
