// SDK Buffer callback regression: replacing output must ignore its prior range.
#include <assert.h>
#include <stdio.h>
#include "../movie_packets.h"

// These accessor semantics match the original SDK's Base/Data/Capacity/SetRange;
// the adapter deliberately has no dependency on this fixture's struct layout.
typedef struct { int offset, size; size_t capacity; unsigned char *base; } buffer;
static unsigned base_calls, capacity_calls, range_calls;
static void *base(const void *p) { base_calls++; return ((const buffer *)p)->base; }
static void *data(const void *p) { const buffer *b = p; return b->base + b->offset; }
static size_t capacity(const void *p) { capacity_calls++; return ((const buffer *)p)->capacity; }
static void range(void *p, int offset, int size) { range_calls++; buffer *b = p; b->offset = offset; b->size = size; }

int main(void) {
    unsigned char arena[256], pcm[32];
    for (unsigned i = 0; i < sizeof pcm; i++) pcm[i] = (unsigned char)(i * 7);
    // Negative control: the previous callback writes behind the intended data
    // and into the canary, then reports the untouched base as the returned PCM.
    memset(arena, 0xA5, sizeof arena);
    buffer old = {64, 7, sizeof pcm, arena + 16};
    memcpy(data(&old), pcm, sizeof pcm); range(&old, 0, sizeof pcm);
    assert(memcmp(old.base, pcm, sizeof pcm));
    assert(arena[16 + sizeof pcm + 32] != 0xA5);

    for (int offset = -8; offset <= 128; offset++) {
        memset(arena, 0xA5, sizeof arena);
        buffer b = {offset, 7, sizeof pcm, arena + 16};
        assert(dm_movie_write_pcm(&b, pcm, sizeof pcm, base, capacity, range));
        assert(b.offset == 0 && b.size == sizeof pcm && b.capacity == sizeof pcm);
        assert(!memcmp(b.base, pcm, sizeof pcm));
        for (unsigned i = 0; i < sizeof arena; i++)
            if (i < 16 || i >= 16 + sizeof pcm) assert(arena[i] == 0xA5);
        // A caller advancing/reusing the range must get the same next output.
        b.offset = 13; b.size = 3;
        assert(dm_movie_write_pcm(&b, pcm, sizeof pcm, base, capacity, range));
        assert(b.offset == 0 && b.size == sizeof pcm && !memcmp(b.base, pcm, sizeof pcm));
    }
    memset(arena, 0xA5, sizeof arena);
    buffer short_buffer = {5, 7, sizeof pcm - 1, arena + 16};
    assert(!dm_movie_write_pcm(&short_buffer, pcm, sizeof pcm, base, capacity, range));
    assert(short_buffer.offset == 0 && short_buffer.size == 0);
    for (unsigned i = 0; i < sizeof arena; i++) assert(arena[i] == 0xA5);
    buffer empty = {7, 9, sizeof pcm, arena + 16};
    assert(dm_movie_write_pcm(&empty, NULL, 0, base, capacity, range));
    assert(empty.offset == 0 && empty.size == 0);
    assert(!dm_movie_write_pcm(&empty, NULL, 1, base, capacity, range));
    assert(!dm_movie_write_pcm(&empty, pcm, (size_t)INT_MAX + 1, base, capacity, range));
    empty.base = NULL;
    assert(!dm_movie_write_pcm(&empty, pcm, 1, base, capacity, range));
    assert(!dm_movie_write_pcm(NULL, pcm, 1, base, capacity, range));
    assert(base_calls > 0 && capacity_calls > 0 && range_calls > 0);
    puts("movie PCM output: 137 prior offsets, repeat reuse, Base callbacks, capacity/empty rejection and canaries passed; old Data callback fails negative control");
    return 0;
}
