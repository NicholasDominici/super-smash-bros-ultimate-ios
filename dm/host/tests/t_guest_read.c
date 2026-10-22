// Exercise the actual checked copier against mapped, protected, and racing VM.
#include "dm_guest_read.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static uint8_t *alias_memory;
static size_t page_size;
static _Atomic uint64_t bitmap[1];
static _Atomic int running;

static int read_alias(uint64_t address, void *out, size_t length) {
    return dm_copy_guest_regions(address, out, length, 0, 0,
        (uint64_t)(uintptr_t)alias_memory, page_size * 2, bitmap);
}
static void *reader(void *unused) {
    (void)unused;
    while (atomic_load(&running)) {
        uint8_t bytes[32] = {0};
        if (read_alias((uint64_t)(uintptr_t)alias_memory, bytes, sizeof bytes))
            for (unsigned i = 0; i < sizeof bytes; ++i) assert(bytes[i] == 0x5a);
    }
    return NULL;
}
int main(void) {
    page_size = (size_t)getpagesize();
    alias_memory = mmap(NULL, page_size * 2, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON, -1, 0);
    assert(alias_memory != MAP_FAILED && page_size * 2 / 4096 < 64);
    memset(alias_memory, 0x5a, page_size * 2);
    uint64_t address = (uint64_t)(uintptr_t)alias_memory;
    uint64_t first_bits = (1ull << (page_size / 4096)) - 1;
    atomic_store(bitmap, first_bits);
    assert(!mprotect(alias_memory + page_size, page_size, PROT_NONE));
    uint8_t bytes[16] = {0};
    assert(read_alias(address, bytes, sizeof bytes) && bytes[0] == 0x5a);
    assert(!read_alias(address + page_size, bytes, 1));
    assert(!read_alias(address + page_size - 8, bytes, sizeof bytes));
    assert(!read_alias(address - 1, bytes, 1));
    assert(!read_alias(UINT64_MAX - 3, bytes, 8));
    assert(!read_alias(address, bytes, 0));
    // A stale bitmap cannot authorize a crashing CPU memcpy after an unmap.
    assert(!mprotect(alias_memory, page_size, PROT_NONE));
    assert(!read_alias(address, bytes, sizeof bytes));
    assert(!mprotect(alias_memory, page_size, PROT_READ | PROT_WRITE));
    assert(dm_copy_guest_regions(address, bytes, sizeof bytes, address, page_size, 0, 0, NULL));
    assert(!dm_copy_guest_regions(address + page_size - 8, bytes, sizeof bytes, address, page_size, 0, 0, NULL));
    pthread_t thread;
    atomic_store(&running, 1);
    assert(!pthread_create(&thread, NULL, reader, NULL));
    for (unsigned i = 0; i < 10000; ++i) {
        atomic_store(bitmap, 0);
        assert(!mprotect(alias_memory, page_size, PROT_NONE));
        assert(!mprotect(alias_memory, page_size, PROT_READ | PROT_WRITE));
        atomic_store(bitmap, first_bits);
    }
    atomic_store(&running, 0);
    assert(!pthread_join(thread, NULL));
    assert(!munmap(alias_memory, page_size * 2));
    puts("guest mapped reads: bounds, sparse holes, protected pages and 10000 unmap races passed");
    return 0;
}
