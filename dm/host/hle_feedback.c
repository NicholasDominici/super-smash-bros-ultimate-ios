// Native SDK vibration and six-axis transport. Each Npad owns independent
// lifecycle, authored actuator values and sensor history; frameworks stay in iOS.
#include "dm_feedback.h"
#include <math.h>
#include <pthread.h>
#include <stddef.h>
#include <string.h>
#include <stdatomic.h>

_Static_assert(sizeof(dm_vibration_value) == 0x10, "VibrationValue ABI");
_Static_assert(sizeof(dm_vibration_info) == 8, "VibrationDeviceInfo ABI");
_Static_assert(sizeof(dm_six_axis_state) == 0x60, "SixAxisSensorState ABI");
_Static_assert(offsetof(dm_six_axis_state, acc) == 0x10 && offsetof(dm_six_axis_state, dir) == 0x34 &&
               offsetof(dm_six_axis_state, attributes) == 0x58, "SixAxisSensorState field offsets");

enum { STYLE_FULLKEY = 1, STYLE_HANDHELD = 2, SENSOR_CONNECTED = 1, RING_SIZE = 64 };
static const uint64_t output_lease_ns = 250000000, motion_lease_ns = 200000000;
static const double tau = 6.2831853071795864769;
static const dm_vibration_value neutral = {0, 160, 0, 320};
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_once_t once = PTHREAD_ONCE_INIT;
static _Atomic unsigned player_limit = 1;
static unsigned permitted = 1;
typedef struct {
    uint64_t epoch, last_game_tick, produced, last_motion_ns;
    uint64_t vibration_sends, motion_reads, motion_states_returned;
    unsigned connected, foreground, capabilities;
    dm_vibration_value last[2];
    uint64_t updated[2], sequence[2];
    dm_six_axis_state ring[RING_SIZE];
    unsigned have, started[2], fusion[2];
    int drift[2];
    float fusion_parameters[2][2];
    double rotation[3][3], angles[3];
    int aligned;
} feedback_device;
static feedback_device devices[DM_FEEDBACK_MAX_PLAYERS];
static _Atomic unsigned assignments[DM_FEEDBACK_MAX_PLAYERS];
static void initialize(void) {
    for (unsigned p = 0; p < DM_FEEDBACK_MAX_PLAYERS; ++p) {
        feedback_device *dev = &devices[p]; dev->epoch = 1; atomic_store(&assignments[p], p);
        for (int side = 0; side < 2; ++side) {
            dev->last[side] = neutral; dev->fusion[side] = 1; dev->drift[side] = 1;
            dev->fusion_parameters[side][0] = .03f; dev->fusion_parameters[side][1] = .4f;
        }
    }
}
static feedback_device *device(unsigned player) {
    pthread_once(&once, initialize);
    return player < atomic_load(&player_limit) ? &devices[player] : NULL;
}
static void clear_motion(feedback_device *dev) {
    dev->have = 0; dev->last_motion_ns = 0; dev->aligned = 0;
    memset(dev->angles, 0, sizeof dev->angles);
}
static void clear_output(feedback_device *dev, uint64_t now) {
    for (int side = 0; side < 2; ++side) {
        dev->last[side] = neutral; dev->updated[side] = now; ++dev->sequence[side];
    }
}
void dm_feedback_configure_players(unsigned count) {
    if (!count || count > DM_FEEDBACK_MAX_PLAYERS) return;
    pthread_once(&once, initialize);
    pthread_mutex_lock(&lock);
    unsigned prior = atomic_load(&player_limit);
    if (prior != count) for (unsigned p = 0; p < DM_FEEDBACK_MAX_PLAYERS; ++p) {
        feedback_device *dev = &devices[p];
        // Configuration normally happens once before attachment. If a caller
        // resizes later, discard routes and old producer leases consistently.
        atomic_store(&assignments[p], p);
        if (p >= count) dev->connected = dev->foreground = dev->capabilities = 0;
        ++dev->epoch; dev->last_game_tick = 0; clear_motion(dev); clear_output(dev, 0);
    }
    atomic_store(&player_limit, count);
    pthread_mutex_unlock(&lock);
}
void dm_feedback_swap_npad_assignments(unsigned a, unsigned b) {
    if (a >= atomic_load(&player_limit) || b >= atomic_load(&player_limit) || a == b) return;
    pthread_once(&once, initialize);
    pthread_mutex_lock(&lock);
    unsigned pa = atomic_load(&assignments[a]), pb = atomic_load(&assignments[b]);
    atomic_store(&assignments[a], pb); atomic_store(&assignments[b], pa);
    feedback_device *left = &devices[pa], *right = &devices[pb];
    // Sensor start/configuration belongs to the logical handle; physical
    // orientation and callbacks stay with the same physical device.
    for (int side = 0; side < 2; ++side) {
        unsigned start = left->started[side]; left->started[side] = right->started[side]; right->started[side] = start;
        unsigned fusion = left->fusion[side]; left->fusion[side] = right->fusion[side]; right->fusion[side] = fusion;
        int drift = left->drift[side]; left->drift[side] = right->drift[side]; right->drift[side] = drift;
        for (int i = 0; i < 2; ++i) {
            float parameter = left->fusion_parameters[side][i]; left->fusion_parameters[side][i] = right->fusion_parameters[side][i]; right->fusion_parameters[side][i] = parameter;
        }
    }
    clear_motion(left); clear_motion(right); clear_output(left, 0); clear_output(right, 0);
    pthread_mutex_unlock(&lock);
}
static int fresh(uint64_t now, uint64_t then, uint64_t limit) { return then && now >= then && now - then <= limit; }
static float clampf(float x, float lo, float hi) { return x < lo ? lo : x > hi ? hi : x; }
static double norm3(const double v[3]) { return sqrt(v[0]*v[0] + v[1]*v[1] + v[2]*v[2]); }
static void cross3(const double a[3], const double b[3], double out[3]) {
    out[0] = a[1]*b[2] - a[2]*b[1]; out[1] = a[2]*b[0] - a[0]*b[2]; out[2] = a[0]*b[1] - a[1]*b[0];
}
// SDK handle bytes: device type (3 full-key / 4 handheld), Npad id,
// actuator index (0/1) or sensor index (2); unused byte 3 must be zero.
// Full-key ids are independent players. Handheld remains a P1 alias only in
// the legacy single-player configuration. Logical handles survive pad hotplug.
static int handle_style(uint32_t h) {
    if (h & 0xff000000u) return -1;
    unsigned type = h & 255, id = (h >> 8) & 255;
    if (type == 3 && id < atomic_load(&player_limit)) return 0;
    if (type == 4 && id == 0x20 && atomic_load(&player_limit) == 1) return 1;
    return -1;
}
static feedback_device *handle_device(uint32_t h) {
    if (handle_style(h) < 0) return NULL;
    pthread_once(&once, initialize);
    unsigned id = (h & 255) == 4 ? 0 : (h >> 8) & 255;
    return device(atomic_load(&assignments[id]));
}
static int vib_side(uint32_t h) { return handle_style(h) >= 0 && ((h >> 16) & 255) < 2 ? (int)((h >> 16) & 255) : -1; }
static int six_style(uint32_t h) { return ((h >> 16) & 255) == 2 ? handle_style(h) : -1; }
static uint32_t handle_base(uint32_t id, uint32_t style, uint32_t current) {
    unsigned limit = atomic_load(&player_limit);
    if (limit == 1 && id != current) return 0;
    if (id < limit && (style & STYLE_FULLKEY)) return 3 | (id << 8);
    if (limit == 1 && id == 0x20 && (style & STYLE_HANDHELD)) return 4 | (id << 8);
    return 0;
}
int dm_feedback_vibration_handles(uint32_t *out, int max, uint32_t id, uint32_t style, uint32_t current) {
    uint32_t base = handle_base(id, style, current);
    if (!out || max <= 0 || !base) return 0;
    int n = max < 2 ? max : 2;
    for (int i = 0; i < n; i++) out[i] = base | (uint32_t)i << 16;
    return n;
}
int dm_feedback_six_handles(uint32_t *out, int max, uint32_t id, uint32_t style, uint32_t current) {
    uint32_t base = handle_base(id, style, current);
    if (!out || max <= 0 || !base) return 0;
    out[0] = base | 2u << 16; return 1;
}
uint64_t dm_feedback_set_player_device(unsigned player, int c, int f, unsigned caps, uint64_t now) {
    feedback_device *dev = device(player); if (!dev) return 0;
    pthread_mutex_lock(&lock);
    unsigned nc = !!c, nf = !!f, ncap = caps & 7;
    if (nc != dev->connected || nf != dev->foreground || ncap != dev->capabilities) {
        dev->connected = nc; dev->foreground = nf; dev->capabilities = ncap;
        ++dev->epoch; dev->last_game_tick = 0; clear_motion(dev); clear_output(dev, now);
    }
    uint64_t result = dev->epoch; pthread_mutex_unlock(&lock); return result;
}
uint64_t dm_feedback_set_device(int c, int f, unsigned caps, uint64_t now) { return dm_feedback_set_player_device(0, c, f, caps, now); }
uint64_t dm_feedback_player_epoch(unsigned player) {
    feedback_device *dev = device(player); if (!dev) return 0;
    pthread_mutex_lock(&lock); uint64_t e = dev->epoch; pthread_mutex_unlock(&lock); return e;
}
uint64_t dm_feedback_epoch(void) { return dm_feedback_player_epoch(0); }
int dm_feedback_npad_target(uint32_t id, unsigned *player, uint64_t *epoch) {
    pthread_once(&once, initialize);
    pthread_mutex_lock(&lock);
    unsigned limit = atomic_load(&player_limit);
    if (id == 0x20 && limit == 1) id = 0;
    int valid = id < limit;
    unsigned physical = valid ? atomic_load(&assignments[id]) : 0;
    feedback_device *dev = &devices[physical];
    valid = valid && permitted && dev->connected && dev->foreground;
    if (valid) { if (player) *player = physical; if (epoch) *epoch = dev->epoch; }
    pthread_mutex_unlock(&lock);
    return valid;
}
void dm_feedback_game_tick(uint64_t now) {
    pthread_once(&once, initialize);
    pthread_mutex_lock(&lock);
    for (unsigned p = 0; p < atomic_load(&player_limit); ++p) {
        feedback_device *dev = &devices[p];
        if (dev->connected && dev->foreground && now > dev->last_game_tick) dev->last_game_tick = now;
    }
    pthread_mutex_unlock(&lock);
}
static dm_vibration_value effective(feedback_device *dev, int side, uint64_t now) {
    if (!permitted || !dev->connected || !dev->foreground || !(dev->capabilities & (1u << side))) return neutral;
    if (!fresh(now, dev->updated[side], output_lease_ns) && !fresh(now, dev->last_game_tick, output_lease_ns)) return neutral;
    return dev->last[side];
}
void dm_feedback_poll_player(unsigned player, uint64_t now, dm_feedback_output *out) {
    if (!out) return;
    feedback_device *dev = device(player);
    if (!dev) { *out = (dm_feedback_output){.value = {{0,160,0,320}, {0,160,0,320}}}; return; }
    pthread_mutex_lock(&lock);
    *out = (dm_feedback_output){.epoch = dev->epoch, .connected = dev->connected, .foreground = dev->foreground,
        .capabilities = dev->capabilities, .motion_samples = dev->produced,
        .motion_updated_ns = dev->last_motion_ns, .vibration_sends = dev->vibration_sends,
        .motion_reads = dev->motion_reads, .motion_states_returned = dev->motion_states_returned};
    for (int i = 0; i < 2; ++i) {
        out->value[i] = effective(dev, i, now); out->updated_ns[i] = dev->updated[i]; out->sequence[i] = dev->sequence[i];
    }
    pthread_mutex_unlock(&lock);
}
void dm_feedback_poll(uint64_t now, dm_feedback_output *out) { dm_feedback_poll_player(0, now, out); }
static dm_vibration_value clean_value(const dm_vibration_value *v) {
    if (!isfinite(v->amp_low) || !isfinite(v->freq_low) || !isfinite(v->amp_high) || !isfinite(v->freq_high)) return neutral;
    return (dm_vibration_value){clampf(v->amp_low, 0, 1), clampf(v->freq_low, 40, 626),
                                 clampf(v->amp_high, 0, 1), clampf(v->freq_high, 80, 1253)};
}
void dm_feedback_vibration_initialize(uint32_t handle) { (void)vib_side(handle); }
void dm_feedback_vibration_permit(int value) {
    pthread_once(&once, initialize);
    pthread_mutex_lock(&lock);
    if (permitted != !!value) {
        permitted = !!value;
        for (unsigned p = 0; p < DM_FEEDBACK_MAX_PLAYERS; ++p) clear_output(&devices[p], 0);
    }
    pthread_mutex_unlock(&lock);
}
int dm_feedback_vibration_permitted(void) {
    pthread_mutex_lock(&lock); int result = (int)permitted; pthread_mutex_unlock(&lock); return result;
}
static void send_locked(uint32_t h, const dm_vibration_value *v, uint64_t now) {
    int side = vib_side(h); feedback_device *dev = handle_device(h);
    if (side < 0 || !dev || !v) return;
    dev->last[side] = clean_value(v); dev->updated[side] = now; ++dev->sequence[side]; ++dev->vibration_sends;
}
void dm_feedback_vibration_send(uint32_t h, const dm_vibration_value *v, uint64_t now) {
    if (!v) return;
    pthread_once(&once, initialize);
    pthread_mutex_lock(&lock); send_locked(h, v, now); pthread_mutex_unlock(&lock);
}
int dm_feedback_vibration_send_many(const uint32_t *handles, const dm_vibration_value *values, int count, uint64_t now) {
    // Eight players with two actuators each; validate bounds before dereferencing.
    if (count < 0 || count > 16 || (count && (!handles || !values))) return 0;
    pthread_once(&once, initialize);
    pthread_mutex_lock(&lock);
    for (int i = 0; i < count; ++i) send_locked(handles[i], &values[i], now);
    pthread_mutex_unlock(&lock); return 1;
}
void dm_feedback_vibration_actual(uint32_t h, dm_vibration_value *out, uint64_t now) {
    if (!out) return;
    pthread_once(&once, initialize);
    pthread_mutex_lock(&lock);
    int side = vib_side(h); feedback_device *dev = handle_device(h);
    *out = side < 0 || !dev ? neutral : effective(dev, side, now); pthread_mutex_unlock(&lock);
}
void dm_feedback_vibration_info(uint32_t h, dm_vibration_info *out) {
    if (!out) return;
    int side = vib_side(h); *out = (dm_vibration_info){side < 0 ? 0u : 1u, side < 0 ? 0u : (uint32_t)side + 1};
}
static void orthonormalize(feedback_device *dev) {
    double n = norm3(dev->rotation[2]);
    for (int j = 0; j < 3; j++) dev->rotation[2][j] /= n;
    double d = dev->rotation[0][0]*dev->rotation[2][0] + dev->rotation[0][1]*dev->rotation[2][1] + dev->rotation[0][2]*dev->rotation[2][2];
    for (int j = 0; j < 3; j++) dev->rotation[0][j] -= d*dev->rotation[2][j];
    n = norm3(dev->rotation[0]);
    for (int j = 0; j < 3; j++) dev->rotation[0][j] /= n;
    cross3(dev->rotation[2], dev->rotation[0], dev->rotation[1]);
}
static void align_gravity(feedback_device *dev, const double acc[3]) {
    memset(dev->rotation, 0, sizeof dev->rotation); dev->rotation[0][0] = dev->rotation[1][1] = dev->rotation[2][2] = 1;
    double n = norm3(acc);
    if (n > 0.5) for (int j = 0; j < 3; j++) dev->rotation[2][j] = -acc[j]/n;
    if (fabs(dev->rotation[2][0]) > 0.9) { dev->rotation[0][0] = 0; dev->rotation[0][1] = 1; }
    orthonormalize(dev);
}
static int quaternion_matrix(feedback_device *dev, const double q[4]) {
    if (!q) return 0;
    double n = 0;
    for (int i = 0; i < 4; i++) { if (!isfinite(q[i])) return 0; n += q[i]*q[i]; }
    if (!isfinite(n) || n < 1e-12) return 0;
    n = sqrt(n); double x=q[0]/n, y=q[1]/n, z=q[2]/n, w=q[3]/n;
    dev->rotation[0][0]=1-2*(y*y+z*z); dev->rotation[0][1]=2*(x*y-z*w); dev->rotation[0][2]=2*(x*z+y*w);
    dev->rotation[1][0]=2*(x*y+z*w); dev->rotation[1][1]=1-2*(x*x+z*z); dev->rotation[1][2]=2*(y*z-x*w);
    dev->rotation[2][0]=2*(x*z-y*w); dev->rotation[2][1]=2*(y*z+x*w); dev->rotation[2][2]=1-2*(x*x+y*y);
    return 1;
}
static void integrate(feedback_device *dev, const double gyro[3], const double acc[3], double dt) {
    double w[3] = {gyro[0], gyro[1], gyro[2]}, n = norm3(acc);
    int style = dev->started[0] ? 0 : 1;
    if (dev->fusion[style] && fabs(n - 1) < 0.15) {
        double measured[3] = {acc[0]/n, acc[1]/n, acc[2]/n};
        double estimated[3] = {-dev->rotation[2][0], -dev->rotation[2][1], -dev->rotation[2][2]}, e[3];
        cross3(measured, estimated, e);
        for (int j = 0; j < 3; j++) w[j] += 0.5*e[j];
    }
    double rate = norm3(w), theta = rate*dt;
    if (theta < 1e-12) return;
    double k[3] = {w[0]/rate, w[1]/rate, w[2]/rate}, s = sin(theta), c = 1-cos(theta);
    double K[3][3] = {{0,-k[2],k[1]}, {k[2],0,-k[0]}, {-k[1],k[0],0}}, E[3][3], result[3][3];
    for (int i = 0; i < 3; i++) for (int j = 0; j < 3; j++) {
        double kk = 0; for (int m = 0; m < 3; m++) kk += K[i][m]*K[m][j];
        E[i][j] = (i == j) + s*K[i][j] + c*kk;
    }
    for (int i = 0; i < 3; i++) for (int j = 0; j < 3; j++) {
        result[i][j] = 0;
        for (int m = 0; m < 3; m++) result[i][j] += dev->rotation[i][m]*E[m][j];
    }
    memcpy(dev->rotation, result, sizeof dev->rotation); orthonormalize(dev);
}
int dm_feedback_motion_push_player(unsigned player, uint64_t e, const double acc[3], const double gyro[3], const double q[4], uint64_t now) {
    feedback_device *dev = device(player);
    if (!dev || !acc || !gyro || !now) return 0;
    for (int i = 0; i < 3; ++i) if (!isfinite(acc[i]) || !isfinite(gyro[i]) || fabs(acc[i]) > 64 || fabs(gyro[i]) > 100) return 0;
    pthread_mutex_lock(&lock);
    if (e != dev->epoch || !dev->connected || !dev->foreground || !(dev->capabilities & DM_FEEDBACK_MOTION) ||
        (dev->last_motion_ns && now <= dev->last_motion_ns)) { pthread_mutex_unlock(&lock); return 0; }
    uint64_t delta = dev->last_motion_ns ? now - dev->last_motion_ns : 4000000;
    if (delta > motion_lease_ns) { clear_motion(dev); delta = 4000000; }
    // Integrate sensor time only; never integrate through a callback stall.
    double dt = delta <= 50000000 ? delta / 1e9 : 0;
    if (!quaternion_matrix(dev, q)) {
        if (!dev->aligned) align_gravity(dev, acc); else integrate(dev, gyro, acc, dt);
    }
    dev->aligned = 1; dev->last_motion_ns = now;
    dm_six_axis_state *state = &dev->ring[dev->produced % RING_SIZE];
    *state = (dm_six_axis_state){.delta_ns = (int64_t)delta, .sampling = (int64_t)++dev->produced, .attributes = SENSOR_CONNECTED};
    for (int i = 0; i < 3; ++i) {
        dev->angles[i] += gyro[i] / tau * dt;
        state->acc[i] = (float)acc[i]; state->gyro[i] = (float)(gyro[i] / tau); state->angle[i] = (float)dev->angles[i];
        for (int j = 0; j < 3; ++j) state->dir[i * 3 + j] = (float)dev->rotation[j][i];
    }
    if (dev->have < RING_SIZE) ++dev->have;
    pthread_mutex_unlock(&lock); return 1;
}
int dm_feedback_motion_push(uint64_t e, const double acc[3], const double gyro[3], const double q[4], uint64_t now) {
    return dm_feedback_motion_push_player(0, e, acc, gyro, q, now);
}
void dm_feedback_six_start(uint32_t h) {
    pthread_once(&once, initialize); pthread_mutex_lock(&lock);
    int style = six_style(h); feedback_device *dev = handle_device(h);
    if (style < 0 || !dev) { pthread_mutex_unlock(&lock); return; }
    if (!dev->started[style]) { dev->started[style] = 1; clear_motion(dev); }
    pthread_mutex_unlock(&lock);
}
void dm_feedback_six_stop(uint32_t h) {
    pthread_once(&once, initialize); pthread_mutex_lock(&lock);
    int style = six_style(h); feedback_device *dev = handle_device(h);
    if (style >= 0 && dev) dev->started[style] = 0;
    pthread_mutex_unlock(&lock);
}
static void disconnected_state(dm_six_axis_state *s) {
    *s = (dm_six_axis_state){.acc = {0,0,-1}, .dir = {1,0,0, 0,1,0, 0,0,1}};
}
int dm_feedback_six_read(uint32_t h, dm_six_axis_state *out, int max, uint64_t now) {
    if (!out || max <= 0) return 0;
    pthread_once(&once, initialize); pthread_mutex_lock(&lock);
    int style = six_style(h), n = 0; feedback_device *dev = handle_device(h);
    if (!dev) { disconnected_state(out); pthread_mutex_unlock(&lock); return 0; }
    ++dev->motion_reads;
    if (style >= 0 && dev->started[style] && dev->connected && dev->foreground && (dev->capabilities & DM_FEEDBACK_MOTION) && fresh(now, dev->last_motion_ns, motion_lease_ns)) {
        n = max < DM_FEEDBACK_MOTION_MAX ? max : DM_FEEDBACK_MOTION_MAX;
        if ((unsigned)n > dev->have) n = (int)dev->have;
        for (int i = 0; i < n; ++i) out[i] = dev->ring[(dev->produced - 1 - (uint64_t)i) % RING_SIZE];
    }
    dev->motion_states_returned += (uint64_t)n;
    if (!n) disconnected_state(&out[0]);
    pthread_mutex_unlock(&lock); return n;
}
int dm_feedback_six_at_rest(uint32_t h, uint64_t now) {
    dm_six_axis_state s; if (!dm_feedback_six_read(h, &s, 1, now)) return 1;
    double speed = 0, force = 0;
    for (int i = 0; i < 3; ++i) { speed += s.gyro[i] * s.gyro[i]; force += s.acc[i] * s.acc[i]; }
    return speed < .0025 * .0025 && fabs(sqrt(force) - 1) < .08;
}
void dm_feedback_six_set_fusion(uint32_t h, int enabled) {
    pthread_once(&once, initialize); pthread_mutex_lock(&lock);
    int s = six_style(h); feedback_device *dev = handle_device(h);
    if (s >= 0 && dev) dev->fusion[s] = !!enabled;
    pthread_mutex_unlock(&lock);
}
int dm_feedback_six_fusion(uint32_t h) {
    pthread_once(&once, initialize); pthread_mutex_lock(&lock);
    int s = six_style(h); feedback_device *dev = handle_device(h);
    int result = s < 0 || !dev ? 0 : (int)dev->fusion[s]; pthread_mutex_unlock(&lock); return result;
}
void dm_feedback_six_set_fusion_parameters(uint32_t h, float gain, float bias) {
    if (!isfinite(gain) || !isfinite(bias)) return;
    pthread_once(&once, initialize); pthread_mutex_lock(&lock);
    int s = six_style(h); feedback_device *dev = handle_device(h);
    if (s >= 0 && dev) { dev->fusion_parameters[s][0] = clampf(gain, 0, 1); dev->fusion_parameters[s][1] = clampf(bias, 0, 1); }
    pthread_mutex_unlock(&lock);
}
void dm_feedback_six_get_fusion_parameters(uint32_t h, float *gain, float *bias) {
    pthread_once(&once, initialize); pthread_mutex_lock(&lock);
    int s = six_style(h); feedback_device *dev = handle_device(h);
    if (gain) *gain = s < 0 || !dev ? 0 : dev->fusion_parameters[s][0];
    if (bias) *bias = s < 0 || !dev ? 0 : dev->fusion_parameters[s][1];
    pthread_mutex_unlock(&lock);
}
void dm_feedback_six_set_drift(uint32_t h, int mode) {
    if (mode < 0 || mode > 2) return;
    pthread_once(&once, initialize); pthread_mutex_lock(&lock);
    int s = six_style(h); feedback_device *dev = handle_device(h);
    if (s >= 0 && dev) dev->drift[s] = mode;
    pthread_mutex_unlock(&lock);
}
int dm_feedback_six_drift(uint32_t h) {
    pthread_once(&once, initialize); pthread_mutex_lock(&lock);
    int s = six_style(h); feedback_device *dev = handle_device(h);
    int result = s < 0 || !dev ? 1 : dev->drift[s]; pthread_mutex_unlock(&lock); return result;
}
