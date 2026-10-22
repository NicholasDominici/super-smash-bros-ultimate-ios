// Synthetic guard objects exercise the real read-only adapter and route/expiry
// policy. These fixtures contain no game content and make no hardware claims.
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "game_profile.h"
#undef DM_GAME_PROGRAM_ID
#define DM_GAME_PROGRAM_ID 0x01006a800016e000ull
#include "../hle_smash_feedback.c"

module_t g_mod[MAX_MOD]; int g_nmod;
static _Atomic uint64_t clock_ns = 1000000000;
static void (*observers[OBS_MAX])(const uint64_t *);
static int missing_gate;
uint64_t now_ns(void) { return clock_ns; }
void gate_obs_set(int id, void (*fn)(const uint64_t *)) { assert(id > 0 && id < OBS_MAX); observers[id] = fn; }
int gate_obs_present(int id) { return id != missing_gate; }
typedef struct { uint8_t owner[0x200], control[0xb00], status[0x200], input[0x100], raw[0x100], interface[0x20]; } fixture;
static fixture fighters[8];
static uint8_t mappings[8 * 0x50];
int dm_guest_copy_mapped(uint64_t a, void *out, size_t n) {
    uintptr_t b = (uintptr_t)fighters, m = (uintptr_t)mappings;
    int allowed = (a >= b && n <= sizeof fighters && a-b <= sizeof fighters-n) ||
                  (a >= m && n <= sizeof mappings && a-m <= sizeof mappings-n);
    if (allowed) memcpy(out, (const void *)(uintptr_t)a, n);
    return allowed;
}
static void put64(void *p, unsigned o, uint64_t v) { memcpy((uint8_t *)p+o,&v,8); }
static void put32(void *p, unsigned o, int32_t v) { memcpy((uint8_t *)p+o,&v,4); }
static void wire(unsigned p) {
    fixture *f = &fighters[p];
    put64(f->control,0,(uintptr_t)g_mod[0].base+0x4f85de0);
    put64(f->control,8,(uintptr_t)f->owner); put64(f->control,0x110,(uintptr_t)f->input);
    put64(f->owner,0x48,(uintptr_t)f->control); put64(f->owner,0x40,(uintptr_t)f->status);
    put64(f->status,0,(uintptr_t)g_mod[0].base+0x4f89e88); put64(f->status,8,(uintptr_t)f->owner);
    put32(f->input,8,(int32_t)p); put32(f->raw,0x9c,5); put32(f->raw,0xc4,(int32_t)p);
    put64(f->interface,0x10,(uintptr_t)f->raw);
    mappings[p*0x50+0x11] = 3; mappings[p*0x50+0x12] = 3; mappings[p*0x50+0x1b] = 1;
}
static void map(unsigned slot, uint32_t buttons) {
    fixture *f = &fighters[slot]; put32(f->raw,8,(int32_t)buttons);
    uint64_t regs[31] = {[0]=(uintptr_t)mappings,[1]=slot,[3]=(uintptr_t)f->interface};
    observers[OBS_SMASH_MAP_CONTROLS](regs);
}
static void status(unsigned p, int kind, int event) {
    fixture *f = &fighters[p]; put32(f->status,0x98,kind);
    uint64_t regs[31] = {0};
    if (event) { regs[19]=(uintptr_t)f->status; observers[OBS_SMASH_STATUS_COMMITTED](regs); }
    else { regs[0]=(uintptr_t)f->control; observers[OBS_SMASH_CONTROL_HEARTBEAT](regs); }
}
static dm_smash_feedback_output poll(unsigned p) {
    dm_smash_feedback_output out; dm_smash_feedback_poll(p,clock_ns,&out); return out;
}
static void neutral(unsigned p) { dm_smash_feedback_output out=poll(p); assert(!out.hold_mask && !out.impact_mask); }
#ifdef DM_SMASH_STRESS
static void *producer(void *argument) {
    unsigned p=(unsigned)(uintptr_t)argument;
    for(unsigned i=0;i<12000;++i) {
        atomic_fetch_add(&clock_ns,1); map(p,1u<<(p%2?11:10));
        status(p,i%4?GUARD:GUARD_DAMAGE,i%4==0);
    }
    return NULL;
}
static void *lifecycle(void *unused) {
    (void)unused;
    for(unsigned i=0;i<10000;++i) {
        unsigned p=i%8;
        dm_feedback_set_player_device(p,0,0,0,clock_ns);
        dm_feedback_set_player_device(p,1,1,7,clock_ns);
        dm_feedback_swap_npad_assignments(p,(p+1)%8);
    }
    return NULL;
}
#endif
int main(void) {
    dm_feedback_configure_players(8);
    for (unsigned p=0;p<8;++p) dm_feedback_set_player_device(p,1,1,p==1?0:7,clock_ns);
    g_nmod=1; g_mod[0].size=0x4f8a100; g_mod[0].base=calloc(1,g_mod[0].size); assert(g_mod[0].base);
    strcpy(g_mod[0].name,"main"); strcpy(g_mod[0].build_id,"unsupported");
    dm_smash_feedback_install(); assert(!installed);
    strcpy(g_mod[0].build_id,build); dm_smash_feedback_install(); assert(!installed);
    const uint32_t evidence[][2] = {{0x4de560,0xb9409800},{0x4de564,0xd65f03c0},{0x1750e08,0xf9400874},
        {0x17516b4,0x3940458c},{0x1751794,0x3940498c},{0x6b8540,0xf9000401}};
    for (unsigned i=0;i<sizeof evidence/sizeof evidence[0];++i) put32(g_mod[0].base,evidence[i][0],(int32_t)evidence[i][1]);
    missing_gate=OBS_SMASH_STATUS_COMMITTED; dm_smash_feedback_install(); assert(!installed);
    missing_gate=0; dm_smash_feedback_install(); assert(installed);
    for(unsigned p=0;p<8;++p) wire(p);
    // Eight isolated players, with alternating actual guard-trigger sides.
    for(unsigned p=0;p<8;++p) { map(p,1u<<(p%2?11:10)); status(p,GUARD,0); }
    for(unsigned p=0;p<8;++p) { dm_smash_feedback_output out=poll(p); assert(out.hold_mask==(p%2?2u:1u)); assert(!out.impact_mask); }
    status(3,GUARD_DAMAGE,1); dm_smash_feedback_output hit=poll(3);
    assert(hit.hold_mask==2 && hit.impact_mask==2 && hit.impact_sequence);
    assert(dm_smash_feedback_trigger_mode(hit,1,1)==2 && !dm_smash_feedback_trigger_mode(hit,0,1));
    assert(!dm_smash_feedback_trigger_mode(hit,1,0) && !dm_smash_feedback_trigger_mode(hit,1,NAN));
    assert(!dm_smash_feedback_trigger_mode(hit,1,INFINITY) && !dm_smash_feedback_trigger_mode(hit,1,1.1f));
    uint64_t first=hit.impact_sequence; status(3,GUARD_DAMAGE,1); assert(poll(3).impact_sequence>first);
    assert(!poll(2).impact_mask); // same-status reentry must still thump, only its owner.
    clock_ns += 56000000; assert(!poll(3).impact_mask && poll(3).hold_mask==2);
    status(3,GUARD_OFF,1); neutral(3);
    // A pressed trigger assigned to attack/grab cannot get shield resistance.
    mappings[0x11]=0; mappings[0x12]=4; map(0,(1u<<10)|(1u<<11)); status(0,GUARD_DAMAGE,1); neutral(0);
    mappings[0x11]=3; mappings[0x12]=3; map(0,0); status(0,GUARD_DAMAGE,1); neutral(0);
    mappings[0x1b]=0; map(0,1u<<10); status(0,GUARD,0); neutral(0); mappings[0x1b]=1;
    map(0,1u<<10); status(0,GUARD_DAMAGE,1); assert(poll(0).impact_mask==1);
    map(0,0); neutral(0); // actual release immediately cancels even queued impact.
    // CPU/default slots, unrelated module types, bad ownership and arbitrary
    // pointers all fail closed instead of leaking an accent to another pad.
    put32(fighters[0].input,8,-1); map(0,1u<<10); clock_ns+=160000000; status(0,GUARD,0); neutral(0); wire(0);
    put64(fighters[0].status,0,1); status(0,GUARD,0); neutral(0); wire(0);
    put64(fighters[0].owner,0x48,(uintptr_t)fighters[1].control); status(0,GUARD,0); neutral(0); wire(0);
    uint64_t bad[31] = {[0]=1,[1]=0,[3]=UINT64_MAX}; observers[OBS_SMASH_MAP_CONTROLS](bad); neutral(0);
    // Disconnected/replaced and backgrounded contexts reject old cached leases.
    map(0,1u<<10); status(0,GUARD,0); assert(poll(0).hold_mask==1);
    dm_feedback_set_player_device(0,0,1,0,++clock_ns); neutral(0);
    dm_feedback_set_player_device(0,1,1,7,++clock_ns); neutral(0);
    status(0,GUARD_DAMAGE,1); neutral(0); // stale mapping epoch cannot revive it.
    map(0,1u<<10); status(0,GUARD,0); assert(poll(0).hold_mask==1);
    dm_feedback_set_player_device(0,1,0,7,++clock_ns); neutral(0);
    dm_feedback_set_player_device(0,1,1,7,++clock_ns); neutral(0);
    // Assignment swap cancels both cached routes; new observations route to the
    // physical controller now bound to that guest Npad, with no stale impact.
    map(0,1u<<10); status(0,GUARD_DAMAGE,1); assert(poll(0).impact_mask==1);
    dm_feedback_swap_npad_assignments(0,4); neutral(0); neutral(4);
    map(0,1u<<10); status(0,GUARD,0); assert(poll(4).hold_mask==1); neutral(0); assert(!poll(4).impact_mask);
    dm_feedback_vibration_permit(0); neutral(4); dm_feedback_vibration_permit(1); neutral(4);
    clock_ns+=160000000; neutral(4); // both mapping and heartbeat leases expire.
    map(0,1u<<10); neutral(4); // fresh input without a fresh game heartbeat stays quiet.
    status(0,GUARD,0); assert(poll(4).hold_mask==1);
    clock_ns+=160000000; status(0,GUARD,0); neutral(4); // heartbeat cannot renew stale input.
    dm_smash_feedback_poll(8,clock_ns,&hit); assert(!hit.hold_mask && !hit.impact_mask);
    dm_smash_feedback_stats counts; dm_smash_feedback_get_stats(&counts);
    assert(counts.installed && counts.impacts[3]==2 && counts.impacts[2]==0 && counts.mappings && counts.heartbeats);
#ifdef DM_SMASH_STRESS
    pthread_t producers[8], hotplug;
    for(unsigned p=0;p<8;++p) assert(!pthread_create(&producers[p],NULL,producer,(void *)(uintptr_t)p));
    assert(!pthread_create(&hotplug,NULL,lifecycle,NULL));
    for(unsigned i=0;i<80000;++i) { dm_smash_feedback_output out=poll(i%8); assert(!(out.hold_mask&~3u) && !(out.impact_mask&~out.hold_mask)); }
    for(unsigned p=0;p<8;++p) assert(!pthread_join(producers[p],NULL));
    assert(!pthread_join(hotplug,NULL));
#endif
    free(g_mod[0].base);
    puts("Smash guard: exact-build gate, eight player routes, custom controls, impact reentry, stale lifecycle and expiry passed");
}
