// Independent native actuator/motion routing, assignment, hotplug and lifecycle.
// Synthetic SDK values only; this does not assert physical controller behavior.
#include "dm_feedback.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static int near(float a, float b) { return fabsf(a-b) < .00001f; }
static int silent(dm_vibration_value value) { return value.amp_low == 0 && value.amp_high == 0; }
int main(void) {
    const uint64_t t = 1000000000;
    uint64_t epoch[8]; uint32_t handles[16]; dm_vibration_value values[16];
    const double acc[3] = {0,0,-1}, gyro[3] = {0,0,0};
    dm_feedback_configure_players(8);
    for (unsigned p = 0; p < 8; ++p) {
        epoch[p] = dm_feedback_set_player_device(p, 1, 1, 7, t);
        assert(epoch[p]);
        assert(dm_feedback_vibration_handles(handles + p*2, 2, p, 1, 0) == 2);
        assert(handles[p*2] == (3u | p<<8));
        assert(handles[p*2+1] == (0x10003u | p<<8));
        values[p*2] = (dm_vibration_value){(p+1)/16.f, 80+p*20, 0,320};
        values[p*2+1] = (dm_vibration_value){0,160,(p+1)/12.f,400+p*20};
        uint32_t sensor = 0; assert(dm_feedback_six_handles(&sensor, 1, p, 1, 0) == 1);
        assert(sensor == (0x20003u | p<<8)); dm_feedback_six_start(sensor);
    }
    assert(dm_feedback_vibration_send_many(handles, values, 16, t+1));
    for (unsigned p = 0; p < 8; ++p) {
        dm_feedback_output out; dm_feedback_poll_player(p, t+2, &out);
        assert(out.connected && out.vibration_sends == 2);
        assert(!memcmp(out.value, values+p*2, sizeof out.value));
        double own[3] = {0, (double)p/10, 0};
        assert(dm_feedback_motion_push_player(p, epoch[p], acc, own, NULL, t+10));
        dm_six_axis_state state; assert(dm_feedback_six_read(0x20003u | p<<8, &state, 1, t+11) == 1);
        assert(near(state.gyro[1], (float)(p/10.0/6.2831853071795864769)) && state.sampling == 1);
    }
    // A mixed controller without haptics/motion never borrows P1 capabilities.
    epoch[1] = dm_feedback_set_player_device(1, 1, 1, 0, t+20);
    dm_feedback_vibration_send(handles[2], &values[2], t+21);
    dm_feedback_output out; dm_feedback_poll_player(1, t+22, &out);
    assert(out.connected && out.capabilities == 0 && silent(out.value[0]) && silent(out.value[1]));
    assert(!dm_feedback_motion_push_player(1, epoch[1], acc, gyro, NULL, t+23));
    dm_feedback_poll_player(0, t+22, &out); assert(near(out.value[0].amp_low, values[0].amp_low));
    // Disconnect/reuse invalidates only that physical slot's callback epoch.
    uint64_t old = epoch[2];
    dm_feedback_set_player_device(2, 0, 1, 0, t+30);
    epoch[2] = dm_feedback_set_player_device(2, 1, 1, 7, t+31);
    assert(epoch[2] != old);
    assert(!dm_feedback_motion_push_player(2, old, acc, gyro, NULL, t+32));
    assert(dm_feedback_motion_push_player(2, epoch[2], acc, gyro, NULL, t+33));
    dm_feedback_poll_player(2, t+34, &out); assert(silent(out.value[0]) && silent(out.value[1]));
    // Swapping logical IDs changes native output/motion routing, not framework
    // slot identity. Cancel pending output so a previous player's effect cannot
    // spill into the newly assigned player.
    dm_feedback_swap_npad_assignments(0, 3);
    dm_feedback_poll_player(0, t+40, &out); assert(silent(out.value[0]));
    dm_feedback_poll_player(3, t+40, &out); assert(silent(out.value[0]));
    dm_feedback_vibration_send(handles[0], &values[0], t+41);
    dm_feedback_poll_player(0, t+42, &out); assert(silent(out.value[0]));
    dm_feedback_poll_player(3, t+42, &out); assert(near(out.value[0].amp_low, values[0].amp_low));
    double turn[3] = {1,0,0};
    assert(dm_feedback_motion_push_player(3, epoch[3], acc, turn, NULL, t+43));
    dm_six_axis_state state;
    assert(dm_feedback_six_read(0x20003u, &state, 1, t+44) == 1 && state.gyro[0] > .15f);
    assert(dm_feedback_six_read(0x20303u, &state, 1, t+44) == 0);
    // Global suspension invalidates every producer and silences every actuator.
    for (unsigned p = 0; p < 8; ++p) {
        uint64_t before = dm_feedback_player_epoch(p);
        dm_feedback_set_player_device(p, 1, 0, p == 1 ? 0 : 7, t+50);
        assert(!dm_feedback_motion_push_player(p, before, acc, gyro, NULL, t+51));
        dm_feedback_poll_player(p, t+52, &out); assert(silent(out.value[0]) && silent(out.value[1]));
        epoch[p] = dm_feedback_set_player_device(p, 1, 1, 7, t+60);
        dm_feedback_poll_player(p, t+61, &out); assert(silent(out.value[0]) && silent(out.value[1]));
    }
    assert(!dm_feedback_motion_push_player(8, epoch[0], acc, gyro, NULL, t+70));
    dm_feedback_poll_player(8, t+70, &out); assert(!out.connected && silent(out.value[0]));
    dm_feedback_vibration_send(0x00000803u, &values[0], t+70);
    assert(!dm_feedback_vibration_send_many(handles, values, 17, t+70));
    dm_feedback_vibration_permit(0);
    for (unsigned p = 0; p < 8; ++p) {
        dm_feedback_poll_player(p, t+71, &out); assert(silent(out.value[0]) && silent(out.value[1]));
    }
    dm_feedback_vibration_permit(1);
    // A game stall stops every latched value at the existing lease boundary.
    assert(dm_feedback_vibration_send_many(handles, values, 16, t+80));
    dm_feedback_game_tick(t+100);
    for (unsigned p = 0; p < 8; ++p) {
        dm_feedback_poll_player(p, t+250000101, &out); assert(silent(out.value[0]) && silent(out.value[1]));
    }
    // Reconfiguration cannot leave a P1 handle routed to a removed slot.
    dm_feedback_configure_players(1);
    uint64_t resized = dm_feedback_player_epoch(0);
    assert(resized != epoch[0]);
    dm_feedback_set_device(1,1,3,t+300000000);
    dm_feedback_vibration_send(3,&values[0],t+300000001);
    dm_feedback_poll(t+300000002,&out); assert(near(out.value[0].amp_low,values[0].amp_low));
    dm_feedback_poll_player(3,t+300000002,&out); assert(!out.connected);
    puts("feedback players: eight isolated native targets, mixed capabilities, swaps, stale epochs and lifecycle passed");
    return 0;
}
