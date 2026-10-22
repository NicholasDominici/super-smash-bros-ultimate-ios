// Saved render-state identities must survive lookahead and deferred replay.
#include <assert.h>
#include <stdio.h>
#include "../../gfx/nvn/nvn_program_cache.h"

typedef struct { uint64_t serial; nvn_program_key original; } program;

static program *resolve(nvn_program_cache *cache, nvn_program_key key) {
    int created;
    program *p = nvn_program_cache_intern(cache, &key, sizeof *p, &created);
    if (created) {
        p->serial = cache->records.n;
        p->original = key;
    }
    assert(!memcmp(&p->original, &key, sizeof key));
    return p;
}

int main(void) {
    nvn_program_cache cache = {0};
    nvn_program_key first = {{11, 22, 0, 0, 0}};
    program *saved = resolve(&cache, first);
    program saved_value = *saved;
    enum { COUNT = 16384, SNAPSHOTS = 256 };
    program *deferred[SNAPSHOTS];
    program snapshot[SNAPSHOTS];
    for (unsigned i = 0; i < COUNT; i++) {
        nvn_program_key next = {{11, 100 + i, i % 7 ? 0 : 55, 0, 0}};
        program *p = resolve(&cache, next);
        // Re-resolving a tuple must not create another object or mutate it.
        unsigned entries = cache.records.n;
        assert(resolve(&cache, next) == p && cache.records.n == entries);
        if (i < SNAPSHOTS) { deferred[i] = p; snapshot[i] = *p; }
        // Lookahead has long exceeded the former 64-slot ring, growing the
        // hash table repeatedly. The already saved program remains identical.
        assert(resolve(&cache, first) == saved);
        assert(!memcmp(saved, &saved_value, sizeof saved_value));
    }
    for (unsigned i = 0; i < SNAPSHOTS; i++) assert(!memcmp(deferred[i], &snapshot[i], sizeof snapshot[i]));
    // Reinitializing a guest program at the same address gives a fresh serial;
    // this new stage must not alias a previously saved composite.
    nvn_program_key reinitialized = first;
    reinitialized.stage_serial[0] = 900001;
    assert(resolve(&cache, reinitialized) != saved);
    nvn_program_key no_fragment = first;
    no_fragment.stage_serial[1] = 0;
    assert(resolve(&cache, no_fragment) != saved);
    nvn_program_key geometry = first;
    geometry.stage_serial[2] = 77;
    assert(resolve(&cache, geometry) != saved);
    nvn_program_key tessellation = geometry;
    tessellation.stage_serial[3] = 88;
    tessellation.stage_serial[4] = 99;
    assert(resolve(&cache, tessellation) != resolve(&cache, geometry));
    assert(!memcmp(saved, &saved_value, sizeof saved_value));
    assert(cache.records.n == COUNT + 5);
    nvn_program_cache_dispose(&cache);
    assert(cache.records.n == 0 && !cache.records.keys && !cache.record_size);
    puts("program cache: 16384 lookahead combinations, saved/deferred identities and stage reuse passed");
    return 0;
}
