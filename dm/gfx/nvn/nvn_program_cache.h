// Stable composite-program storage for saved render states and lookahead.
// The submit thread interns each original stage-serial tuple once. Records never
// move or expire during the renderer session: state snapshots hold raw pointers
// and pipeline prediction may resolve arbitrarily many other stage combinations.
#pragma once
#include "nvn_hmap.h"

typedef struct { uint64_t stage_serial[5]; } nvn_program_key;
typedef struct { nvn_hmap records; size_t record_size; } nvn_program_cache;

// A new zeroed record is initialized by the caller exactly once, then immutable.
// Serial zero represents an unbound/empty stage; initialized shaders have unique
// nonzero serials, including when a guest program address is reused.
static inline void *nvn_program_cache_intern(nvn_program_cache *cache,
                                            const nvn_program_key *key,
                                            size_t record_size, int *created) {
    if (!record_size || (cache->record_size && cache->record_size != record_size)) abort();
    if (!cache->records.klen) {
        nvn_hm_init(&cache->records, sizeof *key);
        cache->record_size = record_size;
    }
    void *record = nvn_hm_get(&cache->records, key);
    *created = record == NULL;
    if (!record) {
        record = calloc(1, record_size);
        if (!record) abort();
        nvn_hm_put(&cache->records, key, record);
    }
    return record;
}

// Only after every renderer state/snapshot and resolved-program reference is gone.
// Normal replay deliberately never evicts entries from this session-owned cache.
static inline void nvn_program_cache_dispose(nvn_program_cache *cache) {
    nvn_hm_clear(&cache->records, free);
    free(cache->records.keys);
    free(cache->records.vals);
    memset(cache, 0, sizeof *cache);
}
