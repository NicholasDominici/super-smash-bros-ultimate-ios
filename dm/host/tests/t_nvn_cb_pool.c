// Exercise descriptor namespaces beyond the old 64-buffer cap and across reuse.
#include <assert.h>
#include <stdio.h>
#include "../../gfx/nvn/nvn_cb_pool.h"

static unsigned char commands[8192];
static void *stress(void *argument) {
    size_t thread = (size_t)argument;
    for (size_t pass = 0; pass < 10000; pass++) {
        const void *command = &commands[thread * 1024 + pass % 1024];
        int texture, sampler;
        assert(nvn_cb_pool_set(command, 1, (int)thread + 1));
        assert(nvn_cb_pool_set(command, 0, (int)thread + 9));
        nvn_cb_pool_get(command, &texture, &sampler);
        assert(texture == (int)thread + 1 && sampler == (int)thread + 9);
        nvn_cb_pool_forget(command);
        nvn_cb_pool_get(command, &texture, &sampler);
        assert(texture == 0 && sampler == 0);
    }
    return NULL;
}

int main(void) {
    for (size_t i = 0; i < sizeof(commands); i++) {
        assert(nvn_cb_pool_set(&commands[i], 1, (int)i + 256));
        assert(nvn_cb_pool_set(&commands[i], 0, (int)i + 512));
    }
    for (size_t i = 0; i < sizeof(commands); i++) {
        int texture, sampler;
        nvn_cb_pool_get(&commands[i], &texture, &sampler);
        assert(texture == (int)i + 256 && sampler == (int)i + 512);
        // Rebinding the first pool must remove only the corresponding offset.
        assert(nvn_cb_pool_set(&commands[i], 1, 0));
        nvn_cb_pool_get(&commands[i], &texture, &sampler);
        assert(texture == 0 && sampler == (int)i + 512);
        nvn_cb_pool_forget(&commands[i]);
        nvn_cb_pool_get(&commands[i], &texture, &sampler);
        assert(texture == 0 && sampler == 0);
    }
    assert(nvn_cb_pool_count == 0);
    pthread_t threads[8];
    for (size_t i = 0; i < 8; i++) assert(!pthread_create(&threads[i], NULL, stress, (void *)i));
    for (size_t i = 0; i < 8; i++) assert(!pthread_join(threads[i], NULL));
    assert(nvn_cb_pool_count == 0);
    free(nvn_cb_pools);
    puts("descriptor pools: 8192 live buffers, 80000 concurrent lifetimes passed");
    return 0;
}
