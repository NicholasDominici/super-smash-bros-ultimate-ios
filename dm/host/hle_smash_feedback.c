// Main-only, exact-build Smash guard observations. The game supplies input-slot
// ownership, customized guard mappings and committed statuses; no button guess
// can create an impact. All asynchronous state contains copied scalars only.
#include "dm.h"
#include "dm_feedback.h"
#include "smash_feedback.h"
#include <stdatomic.h>

enum { GUARD_ON = 0x1b, GUARD = 0x1c, GUARD_OFF = 0x1d, GUARD_DAMAGE = 0x1e };
static const uint64_t lease_ns = 150000000, impact_ns = 55000000;
static const char build[] = "21450c647b8c5940ed5b68218ea128fd";
static pthread_mutex_t mutex = PTHREAD_MUTEX_INITIALIZER;
static module_t *main_module;
static _Atomic int installed;
typedef struct {
    uint64_t at, epoch;
    uint32_t npad;
    unsigned player, held;
} mapped_input;
typedef struct {
    uint64_t heartbeat, epoch, impact_at, impact_sequence;
    uint32_t npad;
    int status, input_slot;
    unsigned impact_mask;
} player_guard;
static mapped_input inputs[DM_FEEDBACK_MAX_PLAYERS];
static player_guard guards[DM_FEEDBACK_MAX_PLAYERS];
static uint64_t sequence;
static dm_smash_feedback_stats stats;

static int fresh(uint64_t now, uint64_t then, uint64_t lifetime) {
    return then && now >= then && now - then < lifetime;
}
static int read_value(uint64_t address, void *out, size_t length) {
    // Fighter/input allocations may use the SDK's sparse alias allocator.
    // Static main storage also contains the fallback controller. Validate
    // sparse mappings and use a kernel copy to survive concurrent unmaps.
    uint64_t base = main_module ? (uint64_t)(uintptr_t)main_module->base : 0;
    int in_main = main_module && address >= base && length <= main_module->size &&
        address - base <= main_module->size - length;
    if (!address) return 0;
    if (!in_main) return dm_guest_copy_mapped(address, out, length);
    memcpy(out, (const void *)(uintptr_t)address, length);
    return 1;
}
static int pointer_at(uint64_t base, unsigned offset, uint64_t *out) {
    return base <= UINT64_MAX - offset && read_value(base + offset, out, sizeof *out) && *out;
}
static int current_route(const mapped_input *input) {
    unsigned physical; uint64_t epoch;
    return dm_feedback_npad_target(input->npad, &physical, &epoch) &&
        physical == input->player && epoch == input->epoch;
}
static void observe_mapping(const uint64_t *regs) {
    int32_t slot = (int32_t)regs[1];
    if (!installed || slot < 0 || slot >= DM_FEEDBACK_MAX_PLAYERS) return;
    uint64_t raw = 0; uint32_t style = 0, npad = UINT32_MAX, buttons = 0;
    uint8_t left = 0xff, right = 0xff, enabled = 0;
    uint64_t mapping = regs[0];
    unsigned player = 0; uint64_t epoch = 0, now = now_ns();
    int valid = mapping <= UINT64_MAX - (uint64_t)slot * 0x50 - 0x12 &&
        pointer_at(regs[3], 0x10, &raw) &&
        read_value(raw + 0x9c, &style, sizeof style) && style == 5 &&
        read_value(raw + 0xc4, &npad, sizeof npad) &&
        read_value(raw + 8, &buttons, sizeof buttons) &&
        read_value(mapping + (uint64_t)slot * 0x50 + 0x11, &left, 1) &&
        read_value(mapping + (uint64_t)slot * 0x50 + 0x12, &right, 1) &&
        read_value(mapping + (uint64_t)slot * 0x50 + 0x1b, &enabled, 1) &&
        dm_feedback_npad_target(npad, &player, &epoch);
    mapped_input input = {0};
    if (valid) input = (mapped_input){.at = now, .epoch = epoch, .npad = npad, .player = player,
        // Respect both the user's action mapping and their per-name rumble toggle.
        .held = enabled ? ((left == 3 && (buttons & (1u << 10)) ? 1u : 0u) |
                          (right == 3 && (buttons & (1u << 11)) ? 2u : 0u)) : 0};
    pthread_mutex_lock(&mutex);
    ++stats.mappings;
    inputs[slot] = input;
    pthread_mutex_unlock(&mutex);
}
static int control_identity(uint64_t control, int32_t *slot, uint64_t *status) {
    uint64_t vtable = 0, owner = 0, input = 0, owner_control = 0, status_vtable = 0, status_owner = 0;
    uint64_t base = main_module ? (uint64_t)(uintptr_t)main_module->base : 0;
    return pointer_at(control, 0, &vtable) && vtable == base + 0x4f85de0 &&
        pointer_at(control, 8, &owner) && pointer_at(owner, 0x48, &owner_control) && owner_control == control &&
        pointer_at(control, 0x110, &input) && read_value(input + 8, slot, sizeof *slot) &&
        *slot >= 0 && *slot < DM_FEEDBACK_MAX_PLAYERS &&
        pointer_at(owner, 0x40, status) && pointer_at(*status, 0, &status_vtable) &&
        status_vtable == base + 0x4f89e88 && pointer_at(*status, 8, &status_owner) && status_owner == owner;
}
static void publish_control(uint64_t control, uint64_t expected_status, int transition) {
    int32_t slot = -1, status = -1; uint64_t status_module = 0;
    if (!installed || !control_identity(control, &slot, &status_module) ||
        (expected_status && expected_status != status_module) ||
        !read_value(status_module + 0x98, &status, sizeof status)) return;
    uint64_t now = now_ns();
    pthread_mutex_lock(&mutex);
    if (transition) ++stats.transitions; else ++stats.heartbeats;
    mapped_input input = inputs[slot];
    if (fresh(now, input.at, lease_ns) && current_route(&input)) {
        player_guard *guard = &guards[input.player];
        if (guard->epoch != input.epoch || guard->npad != input.npad || guard->input_slot != slot)
            *guard = (player_guard){0};
        guard->heartbeat = now; guard->epoch = input.epoch; guard->npad = input.npad;
        guard->input_slot = slot; guard->status = status;
        if (transition && status == GUARD_DAMAGE && input.held) {
            guard->impact_sequence = ++sequence; guard->impact_at = now; guard->impact_mask = input.held;
            ++stats.impacts[input.player];
        } else if (status != GUARD_ON && status != GUARD && status != GUARD_DAMAGE) {
            guard->impact_at = 0; guard->impact_mask = 0;
        }
    }
    pthread_mutex_unlock(&mutex);
}
static void observe_status(const uint64_t *regs) {
    uint64_t status = regs[19], owner = 0, control = 0;
    if (installed && pointer_at(status, 8, &owner) && pointer_at(owner, 0x48, &control))
        publish_control(control, status, 1);
}
static void observe_heartbeat(const uint64_t *regs) { publish_control(regs[0], 0, 0); }

void dm_smash_feedback_poll(unsigned player, uint64_t now, dm_smash_feedback_output *out) {
    if (!out) return;
    *out = (dm_smash_feedback_output){0};
    if (!installed || player >= DM_FEEDBACK_MAX_PLAYERS) return;
    pthread_mutex_lock(&mutex);
    player_guard *guard = &guards[player];
    int admitted = 0;
    if (guard->input_slot >= 0 && guard->input_slot < DM_FEEDBACK_MAX_PLAYERS) {
        mapped_input input = inputs[guard->input_slot];
        if (fresh(now, guard->heartbeat, lease_ns) && fresh(now, input.at, lease_ns) &&
            input.player == player && input.epoch == guard->epoch && input.npad == guard->npad && current_route(&input)) {
            unsigned holding = guard->status == GUARD_ON || guard->status == GUARD || guard->status == GUARD_DAMAGE;
            out->epoch = guard->epoch;
            out->hold_mask = holding ? input.held : 0;
            out->impact_mask = holding && fresh(now, guard->impact_at, impact_ns) ? guard->impact_mask & input.held : 0;
            out->impact_ns = guard->impact_at; out->impact_sequence = guard->impact_sequence;
            admitted = 1;
        }
    }
    if (!admitted) *guard = (player_guard){0};
    pthread_mutex_unlock(&mutex);
}
void dm_smash_feedback_get_stats(dm_smash_feedback_stats *out) {
    if (!out) return;
    pthread_mutex_lock(&mutex); *out = stats; out->installed = installed; pthread_mutex_unlock(&mutex);
}
void dm_smash_feedback_install(void) {
    if (DM_GAME_PROGRAM_ID != 0x01006a800016e000ull || installed) return;
    module_t *candidate = NULL;
    for (int i = 0; i < g_nmod; ++i) if (!strcmp(g_mod[i].name, "main")) candidate = &g_mod[i];
    if (!candidate || !candidate->base || strcmp(candidate->build_id, build) ||
        candidate->size <= 0x4f8a080 || !gate_obs_present(OBS_SMASH_MAP_CONTROLS) ||
        !gate_obs_present(OBS_SMASH_STATUS_COMMITTED) || !gate_obs_present(OBS_SMASH_CONTROL_HEARTBEAT)) return;
    main_module = candidate;
    // These instructions lie outside the rewritten observation sites. They
    // independently validate the exact owner/status/mapping layouts we read.
    const struct { uint32_t offset, word; } guards_words[] = {
        {0x4de560, 0xb9409800}, {0x4de564, 0xd65f03c0}, // current status+0x98
        {0x1750e08, 0xf9400874}, // RawController from interface+0x10
        {0x17516b4, 0x3940458c}, {0x1751794, 0x3940498c}, // Pro ZL/ZR mapping
        {0x6b8540, 0xf9000401}, // owner BOMA at ControlModule+8
    };
    for (unsigned i = 0; i < sizeof guards_words / sizeof guards_words[0]; ++i) {
        uint32_t word = 0;
        if (!read_value((uint64_t)(uintptr_t)candidate->base + guards_words[i].offset, &word, sizeof word) || word != guards_words[i].word) {
            main_module = NULL; return;
        }
    }
    installed = 1;
    gate_obs_set(OBS_SMASH_MAP_CONTROLS, observe_mapping);
    gate_obs_set(OBS_SMASH_STATUS_COMMITTED, observe_status);
    gate_obs_set(OBS_SMASH_CONTROL_HEARTBEAT, observe_heartbeat);
    LOG("Smash feedback: exact 13.0.5 per-player guard mappings, committed status and heartbeat observers enabled");
}
