// Exercise the real SDK adapters with synthetic front-end controller callbacks.
// No game binary, physical controller or platform framework is involved.
#include "../hle.h"
#include "../front.h"
#undef HLE_FORCE
#define HLE_FORCE(mangled, why, ret, cname, ...) static ret cname(__VA_ARGS__)
#undef DM_GAME_LOCAL_PLAYERS
#ifdef DM_TEST_SINGLE_PLAYER
#define DM_GAME_LOCAL_PLAYERS 1
#else
#define DM_GAME_LOCAL_PLAYERS 8
#endif
#include "../hle_hid.c"
#include <assert.h>
#include <stdio.h>

static unsigned signalled, assignments_changed;
static void assignment_changed(void) { ++assignments_changed; }
int dm_opmode(void) { return 0; } // Multiplayer must still expose full-key IDs.
uint64_t now_ns(void) { return 1000000000; }
uint64_t dm_guest_frame(void) { return 0; }
void hle_bind_system_event(void *event, int clear) { (void)event; (void)clear; }
void hle_signal_system_event(void *event) { assert(event); ++signalled; }
void dm_touch_set(const dm_touch *t, int n) { (void)t; (void)n; }
int touch_fill_n(void *out, int max, uint64_t now) { (void)out; (void)max; (void)now; return 0; }

#if defined(DM_HID_STRESS) && !defined(DM_TEST_SINGLE_PLAYER)
static _Atomic uint64_t stress_epoch[8];
static void *input_producer(void *argument) {
    unsigned p = (unsigned)(uintptr_t)argument;
    int x = 1000 + (int)p;
    for (int i = 0; i < 20000; ++i) dm_pad_set_player(p, atomic_load(&stress_epoch[p]), 1ull<<p, x, -x, 2*x, -2*x);
    return NULL;
}
static void *input_hotplug(void *unused) {
    (void)unused;
    for (unsigned i = 0; i < 10000; ++i) {
        unsigned p = i%8; dm_pad_connect_player(p,0);
        atomic_store(&stress_epoch[p],dm_pad_connect_player(p,1));
    }
    return NULL;
}
static void input_stress(void) {
    pthread_t producers[8], hotplug;
    uint32_t a=0,b=1; h_hid_Swap(&a,&b); // Restore the earlier deterministic swap.
    for (unsigned p=0;p<8;++p) {
        atomic_store(&stress_epoch[p],dm_pad_connect_player(p,1));
        assert(!pthread_create(producers+p,NULL,input_producer,(void *)(uintptr_t)p));
    }
    assert(!pthread_create(&hotplug,NULL,input_hotplug,NULL));
    for (int i=0;i<20000;++i) for (uint32_t p=0;p<8;++p) {
        NpadState state; h_hid_StateFullKey(&state,&p);
        assert(state.lx == -state.ly && state.rx == -state.ry);
        if (state.lx) assert(state.lx == 1000+(int)p && state.rx == state.lx*2);
        if (!state.attributes) assert(!state.buttons && !state.lx && !state.rx);
    }
    pthread_join(hotplug,NULL);
    for (unsigned p=0;p<8;++p) pthread_join(producers[p],NULL);
    puts("HID concurrent indexed callback/hotplug/game polling stress passed");
}
#endif

int main(void) {
    NpadState state;
    struct { NpadGcState state; uint64_t sentinel; } gc = {.sentinel = 0x123456789abcdef0ull};
    uint32_t gcid = 0; h_hid_StateGc(&gc.state, &gcid);
    assert(gc.state.sampling > 0 && !gc.state.attributes && !gc.state.left_trigger && !gc.state.right_trigger);
    assert(gc.sentinel == 0x123456789abcdef0ull);
#ifdef DM_TEST_SINGLE_PLAYER
    uint32_t id = 0x20;
    assert(dm_input_max_players() == 1 && h_hid_GetStyle(&id) == STYLE_HANDHELD);
    dm_input_set(DM_BTN_A, 100, 200, 300, 400);
    h_hid_StateHandheld(&state, &id); assert(state.buttons == DM_BTN_A && state.lx == 100 && state.ry == 400);
    dm_input_set(0,0,0,0,0); dm_pad_set(DM_BTN_B, -100,0,0,0);
    h_hid_StateHandheld(&state, &id); assert(state.buttons == DM_BTN_B && state.lx == -100);
    assert(!dm_pad_connect_player(1,1));
    int32_t info[2]; h_hid_ShowCtrl(info, NULL); assert(info[0] == 1 && info[1] == 0x20);
    puts("HID legacy handheld input and controller applet passed");
#else
    uint64_t epochs[8]; uint32_t ids[8] = {0,1,2,3,4,5,6,7};
    assert(dm_input_max_players() == 8);
    uint32_t two = 1; int event = 0;
    h_hid_BindStyleEv(&two, &event, 1); assert(signalled == 0);
    for (unsigned p = 0; p < 8; ++p) {
        epochs[p] = dm_pad_connect_player(p,1); assert(epochs[p]);
        assert(dm_pad_set_player(p, epochs[p], 1ull<<p, 1000+(int)p, -(int)p, 2000+(int)p, 0));
    }
    assert(signalled >= 1);
    for (unsigned p = 0; p < 8; ++p) {
        assert(h_hid_GetStyle(ids+p) == STYLE_FULLKEY);
        h_hid_StateFullKey(&state, ids+p);
        assert(state.buttons == (1ull<<p) && state.lx == 1000+(int)p && state.rx == 2000+(int)p);
        assert(state.attributes & ATTR_CONNECTED);
    }
    // Poll P1 repeatedly between P2's short press and its first game read.
    dm_pad_set_player(1,epochs[1],DM_BTN_X,0,0,0,0);
    dm_pad_set_player(1,epochs[1],0,0,0,0,0);
    for (int i = 0; i < 20; ++i) h_hid_StateFullKey(&state, ids);
    h_hid_StateFullKey(&state, ids+1); assert(state.buttons == DM_BTN_X);
    h_hid_StateFullKey(&state, ids+1); assert(state.buttons == 0);
    dm_pad_connect_player(1,0);
    assert(!h_hid_GetStyle(ids+1));
    h_hid_StateFullKey(&state, ids+1); assert(!state.attributes && !state.buttons && !state.lx);
    assert(!dm_pad_set_player(1,epochs[1],DM_BTN_A,32767,0,0,0));
    uint64_t replacement = dm_pad_connect_player(1,1); assert(replacement != epochs[1]);
    assert(!dm_pad_set_player(1,epochs[1],DM_BTN_A,32767,0,0,0));
    assert(dm_pad_set_player(1,replacement,DM_BTN_Y,123,0,0,0));
    h_hid_StateFullKey(&state, ids+1); assert(state.buttons == DM_BTN_Y && state.lx == 123);
    h_hid_StateFullKey(&state, ids); assert(state.buttons == DM_BTN_A && state.lx == 1000);
    // Touch is confined to its P1 physical slot and follows assignment swaps.
    dm_input_set(DM_BTN_PLUS,0,0,0,0);
    h_hid_StateFullKey(&state, ids+1); assert(!(state.buttons & DM_BTN_PLUS));
    dm_pad_set_assignment_callback(assignment_changed);
    h_hid_Swap(ids, ids+1);
    assert(assignments_changed == 1 && dm_pad_logical_player(0) == 1 && dm_pad_logical_player(1) == 0);
    h_hid_StateFullKey(&state, ids); assert(state.buttons == DM_BTN_Y && state.lx == 123);
    h_hid_StateFullKey(&state, ids+1); assert(state.buttons == (DM_BTN_A | DM_BTN_PLUS) && state.lx == 1000);
    dm_vibration_value effect = {.amp_low=.3f,.freq_low=160,.freq_high=320};
    dm_feedback_set_player_device(1,1,1,3,now_ns());
    uint32_t handles[2]; assert(h_hid_VibHandles(handles,2,ids,STYLE_FULLKEY) == 2);
    h_hid_SendVib(handles,&effect);
    dm_feedback_output feedback; dm_feedback_poll_player(1,now_ns(),&feedback); assert(feedback.value[0].amp_low == .3f);
    // Supported-ID filtering must not accidentally consume hidden players.
    h_hid_SetIds(ids,1); assert(h_hid_GetStyle(ids) && !h_hid_GetStyle(ids+1));
    h_hid_SetIds(ids,8); h_hid_SetStyles(STYLE_JOYDUAL); assert(!h_hid_GetStyle(ids));
    h_hid_SetStyles(STYLE_FULLKEY);
    int32_t info[2]; h_hid_ShowCtrl(info,NULL); assert(info[0] == 8 && info[1] == 0);
    assert(!dm_pad_connect_player(8,1));
    // A touch press/release that has not been consumed must not reappear after
    // suspension. Also clear the legacy scripted input path and its latch.
    dm_input_set(DM_BTN_MINUS,0,0,0,0); dm_input_set(0,0,0,0,0);
    dm_pad_set(DM_BTN_R,0,0,0,0); dm_pad_set(0,0,0,0,0);
    dm_pad_release_players();
    for (unsigned p = 0; p < 8; ++p) {
        h_hid_StateFullKey(&state,ids+p); assert(state.buttons == 0 && state.lx == 0 && state.rx == 0);
    }
    puts("HID players: independent state/latches, hotplug, stale callbacks, assignment and SDK vibration routing passed");
#ifdef DM_HID_STRESS
    input_stress();
#endif
#endif
    return 0;
}
