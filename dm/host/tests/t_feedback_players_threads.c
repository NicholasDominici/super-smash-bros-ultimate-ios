// Concurrent eight-player publication, native batches, assignment and lifecycle.
// Suitable for ThreadSanitizer; all values are synthetic.
#include "dm_feedback.h"
#include <assert.h>
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>

static _Atomic uint64_t clock_ns = 1000000000;
static uint64_t clock_tick(void) { return atomic_fetch_add(&clock_ns,10000) + 10000; }
static void *motion(void *argument) {
    unsigned p = (unsigned)(uintptr_t)argument;
    double a[3] = {0,0,-1}, g[3] = {p/10.0,0,0};
    for (int i = 0; i < 10000; ++i) dm_feedback_motion_push_player(p,dm_feedback_player_epoch(p),a,g,NULL,clock_tick());
    return NULL;
}
static void *native(void *unused) {
    (void)unused; uint32_t h[16]; dm_vibration_value v[16];
    for (unsigned p = 0; p < 8; ++p) for (unsigned side = 0; side < 2; ++side) {
        h[p*2+side] = 3u | p<<8 | side<<16;
        v[p*2+side] = (dm_vibration_value){.amp_low=(p+1)/10.f,.freq_low=160,.amp_high=.1f,.freq_high=320};
    }
    for (int i = 0; i < 10000; ++i) assert(dm_feedback_vibration_send_many(h,v,16,clock_tick()));
    return NULL;
}
static void *lifecycle(void *unused) {
    (void)unused;
    for (unsigned i = 0; i < 3000; ++i) {
        unsigned p = i%8;
        dm_feedback_set_player_device(p,i&1,!(i%3),7,clock_tick());
        dm_feedback_game_tick(clock_tick());
        if (!(i%17)) dm_feedback_swap_npad_assignments(p,(p+1)%8);
    }
    return NULL;
}
int main(void) {
    dm_feedback_configure_players(8);
    pthread_t producers[8], writer, life;
    for (unsigned p = 0; p < 8; ++p) {
        dm_feedback_set_player_device(p,1,1,7,clock_tick()); dm_feedback_six_start(0x20003u | p<<8);
        assert(!pthread_create(producers+p,NULL,motion,(void *)(uintptr_t)p));
    }
    assert(!pthread_create(&writer,NULL,native,NULL)); assert(!pthread_create(&life,NULL,lifecycle,NULL));
    uint64_t epochs[8] = {0}, samples[8] = {0};
    for (unsigned i = 0; i < 10000; ++i) for (unsigned p = 0; p < 8; ++p) {
        dm_feedback_output out; dm_feedback_poll_player(p,clock_tick(),&out);
        assert(out.epoch >= epochs[p] && out.motion_samples >= samples[p]);
        epochs[p] = out.epoch; samples[p] = out.motion_samples;
        for (unsigned side = 0; side < 2; ++side) {
            dm_vibration_value v = out.value[side];
            assert(isfinite(v.amp_low) && v.amp_low >= 0 && v.amp_low <= 1);
            assert(isfinite(v.freq_high));
            assert((out.connected && out.foreground) || (v.amp_low == 0 && v.amp_high == 0));
        }
        dm_six_axis_state states[16]; int n = dm_feedback_six_read(0x20003u | p<<8,states,16,clock_tick());
        assert(n >= 0 && n <= 16);
        for (int j = 1; j < n; ++j) assert(states[j-1].sampling-states[j].sampling == 1);
    }
    for (unsigned p = 0; p < 8; ++p) pthread_join(producers[p],NULL);
    pthread_join(writer,NULL); pthread_join(life,NULL);
    puts("feedback players concurrent stress passed"); return 0;
}
