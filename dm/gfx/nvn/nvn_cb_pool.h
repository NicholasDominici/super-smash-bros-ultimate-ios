// Descriptor numbering follows each command buffer's lifetime, including reuse.
#pragma once
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>

static struct nvn_cb_pool_entry { const void *command; int texture, sampler; } *nvn_cb_pools;
static size_t nvn_cb_pool_count, nvn_cb_pool_capacity;
static pthread_mutex_t nvn_cb_pool_mutex = PTHREAD_MUTEX_INITIALIZER;

static int nvn_cb_pool_set(const void *command, int texture, int base) {
    pthread_mutex_lock(&nvn_cb_pool_mutex);
    size_t i = 0;
    while (i < nvn_cb_pool_count && nvn_cb_pools[i].command != command) i++;
    if (i == nvn_cb_pool_count && base) {
        if (i == nvn_cb_pool_capacity) {
            size_t capacity = nvn_cb_pool_capacity ? nvn_cb_pool_capacity * 2 : 64;
            if (capacity < nvn_cb_pool_capacity || capacity > SIZE_MAX / sizeof(*nvn_cb_pools)) {
                pthread_mutex_unlock(&nvn_cb_pool_mutex); return 0;
            }
            void *next = realloc(nvn_cb_pools, capacity * sizeof(*nvn_cb_pools));
            if (!next) { pthread_mutex_unlock(&nvn_cb_pool_mutex); return 0; }
            nvn_cb_pools = next; nvn_cb_pool_capacity = capacity;
        }
        nvn_cb_pools[nvn_cb_pool_count++] = (struct nvn_cb_pool_entry){command, 0, 0};
    }
    if (i < nvn_cb_pool_count) {
        if (texture) nvn_cb_pools[i].texture = base;
        else nvn_cb_pools[i].sampler = base;
    }
    pthread_mutex_unlock(&nvn_cb_pool_mutex); return 1;
}

static void nvn_cb_pool_get(const void *command, int *texture, int *sampler) {
    *texture = *sampler = 0;
    pthread_mutex_lock(&nvn_cb_pool_mutex);
    for (size_t i = 0; i < nvn_cb_pool_count; i++) if (nvn_cb_pools[i].command == command) {
        *texture = nvn_cb_pools[i].texture; *sampler = nvn_cb_pools[i].sampler; break;
    }
    pthread_mutex_unlock(&nvn_cb_pool_mutex);
}

static void nvn_cb_pool_forget(const void *command) {
    pthread_mutex_lock(&nvn_cb_pool_mutex);
    for (size_t i = 0; i < nvn_cb_pool_count; i++) if (nvn_cb_pools[i].command == command) {
        nvn_cb_pools[i] = nvn_cb_pools[--nvn_cb_pool_count]; break;
    }
    pthread_mutex_unlock(&nvn_cb_pool_mutex);
}
