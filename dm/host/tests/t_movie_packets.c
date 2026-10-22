// Actual stb_vorbis Flush resynchronization must retain its unconsumed tail.
#include <assert.h>
#include <stdio.h>
#include "../movie_packets.h"
#define STB_VORBIS_NO_STDIO
#define STB_VORBIS_NO_PULLDATA_API
#define STB_VORBIS_NO_INTEGER_CONVERSION
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Weverything"
#include "../../third_party/stb_vorbis/stb_vorbis.c"
#pragma clang diagnostic pop

// Generated container pages only; no encoded audio, game data or binary fixture.
static size_t make_page(uint8_t *page, unsigned sequence) {
    enum { PAYLOAD = 31, LENGTH = 27 + 1 + PAYLOAD };
    memset(page, 0, LENGTH);
    memcpy(page, "OggS", 4); page[26] = 1; page[27] = PAYLOAD;
    page[6] = (uint8_t)sequence; page[14] = 42; page[18] = (uint8_t)sequence;
    memset(page + 28, (int)(0x30 + sequence), PAYLOAD);
    uint32_t crc = 0;
    for (size_t i = 0; i < LENGTH; i++) crc = crc32_update(crc, page[i]);
    for (unsigned i = 0; i < 4; i++) page[22 + i] = (uint8_t)(crc >> (8 * i));
    return LENGTH;
}

static int scan(stb_vorbis *decoder, const uint8_t *data, size_t size) {
    int samples = -1;
    int used = stb_vorbis_decode_frame_pushdata(decoder, data, (int)size, NULL, NULL, &samples);
    assert(samples == 0 && used >= 0 && (size_t)used <= size);
    return used;
}

int main(void) {
    crc32_init();
    uint8_t first[64], second[64], third[64];
    size_t n = make_page(first, 1);
    assert(make_page(second, 2) == n && make_page(third, 3) == n);
    stb_vorbis decoder = {.push_mode = 1};
    stb_vorbis_flush_pushdata(&decoder);
    dm_movie_bytes bytes = {0};
    assert(dm_movie_bytes_append(&bytes, first, n, 256));
    int used = scan(&decoder, bytes.data, bytes.size);
    assert(used == (int)n - 3 && decoder.page_crc_tests >= 0);
    assert(dm_movie_bytes_consume(&bytes, (size_t)used) && bytes.size == 3);
    assert(!memcmp(bytes.data, first + n - 3, 3));
    assert(dm_movie_bytes_append(&bytes, second, n, 256));
    used = scan(&decoder, bytes.data, bytes.size);
    assert(used == 3 && decoder.page_crc_tests == -1);
    assert(dm_movie_bytes_consume(&bytes, (size_t)used));
    assert(bytes.size == n && !memcmp(bytes.data, second, n));

    // The former one-page/free behavior supplies the next page in place of
    // those three bytes, so the actual CRC scanner cannot resynchronize.
    stb_vorbis lost_tail = {.push_mode = 1};
    stb_vorbis_flush_pushdata(&lost_tail);
    assert(scan(&lost_tail, first, n) == (int)n - 3);
    scan(&lost_tail, second, n);
    scan(&lost_tail, third, n);
    assert(lost_tail.page_crc_tests >= 0);

    // A new Flush discards bytes from the old position before accepting new
    // pages. Oversized appends/consumes fail without corrupting retained data.
    dm_movie_bytes_clear(&bytes);
    stb_vorbis_flush_pushdata(&decoder);
    assert(dm_movie_bytes_append(&bytes, third, n, n));
    assert(!dm_movie_bytes_append(&bytes, first, 1, n));
    assert(bytes.size == n && !memcmp(bytes.data, third, n));
    assert(!dm_movie_bytes_consume(&bytes, n + 1));
    used = scan(&decoder, bytes.data, bytes.size);
    assert(dm_movie_bytes_consume(&bytes, (size_t)used) && bytes.size == 3);
    assert(dm_movie_bytes_append(&bytes, first, n, 256));
    used = scan(&decoder, bytes.data, bytes.size);
    assert(used == 3 && decoder.page_crc_tests == -1);
    assert(dm_movie_bytes_consume(&bytes, (size_t)used));
    assert(bytes.size == n && !memcmp(bytes.data, first, n));
    dm_movie_bytes_dispose(&bytes);
    assert(!bytes.data && !bytes.size && !bytes.capacity);

    enum { CAPACITY = 4 << 20 };
    assert(dm_movie_payload_size(0, CAPACITY, 0, 4, CAPACITY, 1) == 0);
    // Another title may have a valid one-frame final packet filling capacity
    // at timestamp zero. It must reach the decoder unchanged.
    assert(dm_movie_payload_size(0, CAPACITY, 0, 4, CAPACITY, 0) == CAPACITY);
    for (int allow = 0; allow <= 1; allow++) {
        assert(dm_movie_payload_size(0, CAPACITY, -1, 4, CAPACITY, allow) == 0);
        assert(dm_movie_payload_size(0, 173, -1, 4, CAPACITY, allow) == 0);
        assert(dm_movie_payload_size(0, CAPACITY, 0, 0, CAPACITY, allow) == CAPACITY);
        assert(dm_movie_payload_size(0, CAPACITY, 1, 4, CAPACITY, allow) == CAPACITY);
        assert(dm_movie_payload_size(0, 173, 0, 4, CAPACITY, allow) == 173);
        assert(dm_movie_payload_size(8, 173, 0, 4, CAPACITY, allow) == 173);
        assert(dm_movie_payload_size(0, 173, 9000, 4, CAPACITY, allow) == 173);
    }
    puts("movie packets: actual Vorbis Flush CRC recovery, retained bytes, bounds and exact empty-EOS markers passed");
    return 0;
}
