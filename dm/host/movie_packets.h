// Retain bytes not yet consumed by a push decoder, independently of input slots.
#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct { uint8_t *data; size_t size, capacity; } dm_movie_bytes;

static inline int dm_movie_bytes_append(dm_movie_bytes *bytes, const void *data,
                                         size_t size, size_t limit) {
    if (bytes->size > limit || size > limit - bytes->size || (size && !data)) return 0;
    size_t need = bytes->size + size;
    if (need > bytes->capacity) {
        size_t cap = bytes->capacity ? bytes->capacity : (limit < 256 ? limit : 256);
        while (cap < need) cap = cap > limit / 2 ? limit : cap * 2;
        void *p = realloc(bytes->data, cap);
        if (!p) return 0;
        bytes->data = p; bytes->capacity = cap;
    }
    if (size) memcpy(bytes->data + bytes->size, data, size);
    bytes->size = need;
    return 1;
}

static inline int dm_movie_bytes_consume(dm_movie_bytes *bytes, size_t size) {
    if (size > bytes->size) return 0;
    if (size && size < bytes->size) memmove(bytes->data, bytes->data + size, bytes->size - size);
    bytes->size -= size;
    return 1;
}

static inline void dm_movie_bytes_clear(dm_movie_bytes *bytes) { bytes->size = 0; }
static inline void dm_movie_bytes_dispose(dm_movie_bytes *bytes) {
    free(bytes->data); *bytes = (dm_movie_bytes){0};
}

// Negative-timestamp EOS is the existing shared empty-marker convention.
// Only a caller with verified title-specific behavior may enable Smash's
// zero-timestamp/full-capacity convention; other titles may carry real data.
static inline int dm_movie_payload_size(int offset, int size, int64_t pts,
                                        uint32_t flags, uint32_t capacity,
                                        int allow_zero_capacity_eos) {
    if ((flags & 4u) && (pts < 0 || (allow_zero_capacity_eos && pts == 0 && offset == 0 && (uint32_t)size == capacity))) return 0;
    return size;
}
