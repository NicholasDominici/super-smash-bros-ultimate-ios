// Real gate table: collision/tombstone behavior, bounded failure and mutations
// concurrent with dispatch. Addresses and instructions are synthetic test data.
#include <assert.h>
#include <stdatomic.h>
#include <sys/wait.h>
#include <unistd.h>
#include "../hle.c"
struct dm_flags g_flag;
uint64_t unimpl_stubs[4096];
void *hlecount_wrap(const char *kind, const char *name, void *fn) { (void)kind; (void)name; return fn; }
uint64_t guest_ns(void) { return 6250; }
uint64_t svc_dispatch(int number, uint64_t *registers, uint64_t original) { (void)registers; return number + original; }
void thr_svc_enter(uint64_t *registers, uint64_t original) { (void)registers; (void)original; }
void thr_svc_leave(void) {}
static const uint64_t stable = 0x100000004ull;
static _Atomic int running = 1;
static void *dispatcher(void *unused) {
    (void)unused; uint64_t regs[32] = {0};
    while (atomic_load(&running)) assert(gate_dispatch(stable, regs) == 120 && regs[0] == 120);
    return NULL;
}
static void duplicate_fails(void) {
    pid_t p = fork(); assert(p >= 0);
    if (!p) { freopen("/dev/null", "w", stderr); gate_register(stable, "cntpct", 0, 0); _exit(0); }
    int status; waitpid(p, &status, 0); assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
}
static void capacity_boundary(void) {
    int marker[2]; assert(!pipe(marker));
    pid_t p = fork(); assert(p >= 0);
    if (!p) {
        close(marker[0]); freopen("/dev/null", "w", stderr);
        for (unsigned i = 1; i < (1u << GATE_BITS) / 4; i++)
            gate_register(0x800000000ull + (uint64_t)i * 4, "cntpct", 0, 0);
        assert(g_ngate == (1 << GATE_BITS) / 4);
        assert(write(marker[1], "1", 1) == 1);
        gate_register(0x900000000ull, "cntpct", 0, 0); _exit(0);
    }
    close(marker[1]); char ready = 0; assert(read(marker[0], &ready, 1) == 1 && ready == '1'); close(marker[0]);
    int status; waitpid(p, &status, 0); assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
}
static unsigned observations;
static void observe(const uint64_t *regs) { assert(regs); observations++; }
int main(void) {
    uint64_t regs[32] = {0}; gate_register(stable, "cntpct", 0, 0);
    uint64_t collision = stable + 4;
    while (gate_h(collision) != gate_h(stable)) collision += 4;
    gate_register(collision, "svc", 7, 10); assert(gate_dispatch(collision, regs) == 17);
    gate_unregister_range(collision, 4); assert(gate_dispatch(stable, regs) == 120);
    gate_register(collision, "svc", 8, 11); assert(gate_dispatch(collision, regs) == 19);
    gate_unregister_range(collision, 4); duplicate_fails(); capacity_boundary();
    gate_obs_set(1, observe); assert(!gate_obs_present(1));
    gate_register(collision, "obs", 1, 0); gate_register(collision + 4, "obs", 1, 0);
    gate_dispatch(collision, regs); assert(observations == 1 && gate_obs_present(1));
    gate_unregister_range(collision, 4); assert(gate_obs_present(1));
    gate_unregister_range(collision + 4, 4); assert(!gate_obs_present(1));
    pthread_t reader; assert(!pthread_create(&reader, NULL, dispatcher, NULL));
    for (unsigned i = 0; i < 2000; i++) {
        uint64_t address = 0x400000000ull + (uint64_t)i * 0x10000;
        gate_register(address, "svc", 3, i); assert(gate_dispatch(address, regs) == i + 3);
        gate_unregister_range(address, 4);
    }
    atomic_store(&running, 0); pthread_join(reader, NULL);
    assert(g_ngate == 1); gate_unregister_range(stable, 4); assert(g_ngate == 0);
    puts("PASS: gate collision, tombstone reuse, exact 16384 capacity, duplicate/overflow rejection, observer lifetime, 2000 concurrent registration/dispatch/unload cycles");
    return 0;
}
