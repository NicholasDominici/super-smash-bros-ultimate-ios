// Present allocator and UV storage may be reused only after GPU feedback.
// The caller holds the presentation mutex for every access. Logical queue
// retirement (merged, dropped or cancelled frames) never changes this state.
#pragma once
#include <stdint.h>

typedef struct { uint64_t submitted, completed; } nvn_present_slot;

static inline int nvn_present_slot_ready(const nvn_present_slot *slot) {
    return slot->submitted == slot->completed;
}

// Called immediately before a real GPU commit, after successful encoding.
// An encoding cancelled before commit therefore leaves the slot reusable.
static inline int nvn_present_slot_submit(nvn_present_slot *slot, uint64_t ticket) {
    if (!ticket || ticket <= slot->submitted || !nvn_present_slot_ready(slot)) return 0;
    slot->submitted = ticket;
    return 1;
}

// Called by GPU feedback, including an error completion. A stale or duplicate
// callback must not release storage belonging to a newer submission.
static inline int nvn_present_slot_complete(nvn_present_slot *slot, uint64_t ticket) {
    if (ticket != slot->submitted || nvn_present_slot_ready(slot)) return 0;
    slot->completed = ticket;
    return 1;
}
