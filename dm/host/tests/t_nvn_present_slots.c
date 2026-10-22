// Logical present retirement must not release command allocator or UV storage.
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <unistd.h>
#include "../../gfx/nvn/nvn_present_slots.h"

typedef struct {
    pthread_mutex_t mu;
    pthread_cond_t cv;
    nvn_present_slot slot;
    uint64_t logical_done;
    unsigned blocked;
    int acquired;
} fixture;

static void *reuse_slot(void *context) {
    fixture *f = context;
    pthread_mutex_lock(&f->mu);
    while (!nvn_present_slot_ready(&f->slot)) {
        f->blocked++;
        pthread_cond_broadcast(&f->cv);
        pthread_cond_wait(&f->cv, &f->mu);
    }
    // In production, allocator reset and UV overwrite are after this wait.
    assert(nvn_present_slot_submit(&f->slot, 102));
    f->acquired = 1;
    pthread_cond_broadcast(&f->cv);
    pthread_mutex_unlock(&f->mu);
    return NULL;
}

int main(void) {
    alarm(10);   // A broken wait/release protocol must fail instead of hanging CI.
    fixture f = {.mu = PTHREAD_MUTEX_INITIALIZER, .cv = PTHREAD_COND_INITIALIZER};
    assert(nvn_present_slot_ready(&f.slot));
    assert(!nvn_present_slot_submit(&f.slot, 0));
    // A successfully encoded frame owns this slot until its actual feedback.
    assert(nvn_present_slot_submit(&f.slot, 3));
    assert(!nvn_present_slot_submit(&f.slot, 6));
    pthread_t waiter;
    assert(!pthread_create(&waiter, NULL, reuse_slot, &f));
    pthread_mutex_lock(&f.mu);
    while (!f.blocked) pthread_cond_wait(&f.cv, &f.mu);
    assert(!f.acquired);
    // Merging/dropping newer tickets advances the old shared predicate, but
    // must not let this waiter reset an allocator still executing ticket 3.
    f.logical_done = 101;
    unsigned blocked = f.blocked;
    pthread_cond_broadcast(&f.cv);
    while (f.blocked == blocked) pthread_cond_wait(&f.cv, &f.mu);
    assert(f.logical_done > f.slot.submitted && !f.acquired);
    assert(!nvn_present_slot_complete(&f.slot, 2));
    assert(!nvn_present_slot_ready(&f.slot));
    // Both successful and error GPU feedback mean execution has ended. Only
    // that exact submitted ticket releases the waiter and its storage.
    assert(nvn_present_slot_complete(&f.slot, 3));
    pthread_cond_broadcast(&f.cv);
    while (!f.acquired) pthread_cond_wait(&f.cv, &f.mu);
    assert(f.slot.submitted == 102 && f.slot.completed == 3);
    assert(!nvn_present_slot_complete(&f.slot, 3));
    assert(!nvn_present_slot_ready(&f.slot));
    assert(nvn_present_slot_complete(&f.slot, 102));
    assert(nvn_present_slot_ready(&f.slot));
    pthread_mutex_unlock(&f.mu);
    assert(!pthread_join(waiter, NULL));

    nvn_present_slot ring[3] = {{0}};
    for (unsigned i = 0; i < 3; i++) assert(nvn_present_slot_submit(&ring[i], i + 1));
    // Different slots complete independently; shutdown cannot treat one
    // higher-ticket callback as proof that every allocator has completed.
    assert(nvn_present_slot_complete(&ring[2], 3));
    assert(!nvn_present_slot_ready(&ring[0]) && !nvn_present_slot_ready(&ring[1]));
    assert(nvn_present_slot_complete(&ring[0], 1));
    assert(nvn_present_slot_complete(&ring[1], 2));
    for (unsigned i = 0; i < 3; i++) assert(nvn_present_slot_ready(&ring[i]));
    // An encoder cancelled before commit does not submit or reserve a slot.
    // It remains reusable without waiting for nonexistent GPU feedback.
    assert(nvn_present_slot_submit(&ring[0], 7));
    assert(nvn_present_slot_complete(&ring[0], 7));
    assert(!nvn_present_slot_complete(&ring[0], 7));
    assert(!nvn_present_slot_submit(&ring[0], 7));
    assert(!pthread_cond_destroy(&f.cv));
    assert(!pthread_mutex_destroy(&f.mu));
    alarm(0);
    puts("present slots: logical retirement cannot bypass GPU completion; stale feedback, independent slots and reuse passed");
    return 0;
}
