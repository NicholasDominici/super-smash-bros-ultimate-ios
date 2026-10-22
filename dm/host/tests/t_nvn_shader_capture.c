// Synthetic original-byte capture tests: no game fixtures or GPU execution.
#include <assert.h>
#include <dirent.h>
#include <sys/types.h>
#include "../../gfx/nvn/nvn_shader_capture.h"

static uint8_t control[0x850], code[0x90], key[8];
static void u32(uint8_t *p, uint32_t value) { memcpy(p, &value, 4); }
static void fixture(void) {
    memset(control, 0, sizeof control); memset(code, 0, sizeof code);
    u32(control, 0x98761234); u32(control + 0x20, sizeof control);
    u32(control + 0x700, sizeof code); u32(control + 0x704, sizeof code);
    u32(code, 0x12345678); u32(code + 0x30, 1u << 10);
    uint8_t digest[32]; CC_SHA256_CTX hash; CC_SHA256_Init(&hash);
    CC_SHA256_Update(&hash, control, sizeof control); CC_SHA256_Update(&hash, code, sizeof code);
    CC_SHA256_Final(digest, &hash); memcpy(key, digest, 8);
}
static void setup(nvn_capture_state *state, char *path) {
    assert(mkdtemp(path)); nvn_capture_init(state, path, 1); assert(state->active && !state->broken);
}
static void cleanup(nvn_capture_state *state, const char *path) {
    if (state->ledger >= 0) assert(!close(state->ledger));
    if (state->directory >= 0) assert(!close(state->directory));
    free(state->keys); free(state->pending);
    DIR *dir = opendir(path); assert(dir); struct dirent *entry;
    while ((entry = readdir(dir))) {
        if (entry->d_name[0] == '.') continue;
        char file[1024]; snprintf(file, sizeof file, "%s/%s", path, entry->d_name); assert(!unlink(file));
    }
    closedir(dir); assert(!rmdir(path)); pthread_mutex_destroy(&state->mutex);
}
static void good(void) {
    nvn_capture_state state = NVN_CAPTURE_INITIALIZER; char path[] = "/tmp/nvn-capture-good-XXXXXX"; setup(&state, path);
    nvn_capture_program(&state, 1, (void *)0x1000, 2);
    nvn_capture_stage(&state, 1, 0, 0, control, code, 1, key);
    nvn_capture_stage(&state, 1, 1, 0, control, code, 0, NULL);
    assert(state.totals.captured_unique == 1 && state.totals.unresolved_deferred == 1);
    nvn_capture_stage(&state, 1, 1, 1, control, code, 1, key);
    assert(state.totals.duplicates == 1 && !state.totals.unresolved_deferred && !state.totals.failures);
    char name[32]; snprintf(name, sizeof name, "%02x%02x%02x%02x%02x%02x%02x%02x.ctl", key[0], key[1], key[2], key[3], key[4], key[5], key[6], key[7]);
    int fd = openat(state.directory, name, O_RDONLY); assert(fd >= 0); uint8_t bytes[sizeof control];
    assert(read(fd, bytes, sizeof bytes) == sizeof bytes && !memcmp(bytes, control, sizeof bytes));
    assert(read(fd, bytes, 1) == 0); close(fd);
    assert(state.totals.bytes_written == sizeof control + sizeof code);
    // Keep one complete fixture for the strict Python consumer when requested.
    const char *out = getenv("NVN_CAPTURE_TEST_OUTPUT");
    if (out) { assert(!close(state.ledger)); state.ledger = -1; assert(!rename(path, out)); close(state.directory); free(state.keys); free(state.pending); }
    else cleanup(&state, path);
}
static void malformed(unsigned which) {
    fixture(); nvn_capture_state state = NVN_CAPTURE_INITIALIZER; char path[] = "/tmp/nvn-capture-bad-XXXXXX"; setup(&state, path);
    switch (which) {
    case 0: u32(control + 0x20, 0x700); break;
    case 1: u32(control + 0x704, 1u << 24); break;
    case 2: u32(control + 0x700, sizeof code + 1); break;
    case 3: u32(code + 0x30, 7u << 10); break;
    case 4: key[0] ^= 1; break;
    case 5: u32(control, 0); break;
    }
    nvn_capture_program(&state, 2, NULL, 1); nvn_capture_stage(&state, 2, 0, 0, control, code, 1, key);
    assert(state.totals.failures == 1 && !state.totals.captured_unique); cleanup(&state, path);
}
static void collision_and_limit(void) {
    fixture(); nvn_capture_state state = NVN_CAPTURE_INITIALIZER; char path[] = "/tmp/nvn-capture-limits-XXXXXX"; setup(&state, path);
    char name[32]; snprintf(name, sizeof name, "%02x%02x%02x%02x%02x%02x%02x%02x.ctl", key[0], key[1], key[2], key[3], key[4], key[5], key[6], key[7]);
    int fd = openat(state.directory, name, O_WRONLY | O_CREAT | O_EXCL, 0600); assert(fd >= 0); assert(write(fd, "owned", 5) == 5); close(fd);
    nvn_capture_program(&state, 3, NULL, 1); nvn_capture_stage(&state, 3, 0, 0, control, code, 1, key);
    assert(state.totals.failures == 1 && !state.totals.captured_unique);
    fd = openat(state.directory, name, O_RDONLY); char bytes[5]; assert(read(fd, bytes, 5) == 5 && !memcmp(bytes, "owned", 5)); close(fd);
    cleanup(&state, path);
    state = (nvn_capture_state)NVN_CAPTURE_INITIALIZER; char path2[] = "/tmp/nvn-capture-byte-limit-XXXXXX"; setup(&state, path2);
    state.totals.bytes_written = NVN_CAPTURE_MAX_BYTES;
    nvn_capture_program(&state, 4, NULL, 1); nvn_capture_stage(&state, 4, 0, 0, control, code, 1, key);
    assert(state.totals.failures == 1 && !state.totals.captured_unique); cleanup(&state, path2);
}
static nvn_capture_state concurrent = NVN_CAPTURE_INITIALIZER;
static void *thread_capture(void *argument) {
    uint64_t serial = (uintptr_t)argument + 10;
    nvn_capture_program(&concurrent, serial, NULL, 1);
    nvn_capture_stage(&concurrent, serial, 0, 0, control, code, 1, key);
    return NULL;
}
static void threads(void) {
    fixture(); char path[] = "/tmp/nvn-capture-threads-XXXXXX"; setup(&concurrent, path);
    pthread_t workers[16]; for (uintptr_t i = 0; i < 16; i++) assert(!pthread_create(&workers[i], NULL, thread_capture, (void *)i));
    for (unsigned i = 0; i < 16; i++) assert(!pthread_join(workers[i], NULL));
    assert(concurrent.totals.captured_unique == 1 && concurrent.totals.duplicates == 15 && !concurrent.totals.failures);
    assert(concurrent.totals.programs == 16 && concurrent.totals.register_stages == 16); cleanup(&concurrent, path);
}
int main(void) {
    fixture(); good(); for (unsigned i = 0; i < 6; i++) malformed(i); collision_and_limit(); threads();
    puts("shader capture: exact bytes, deferred resolution, invalid bounds, exclusive writes, byte cap, 16 concurrent registrations passed");
    return 0;
}
