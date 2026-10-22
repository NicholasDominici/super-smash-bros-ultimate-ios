// Synthetic Mii service contract tests. Fixture helpers stand in for SDK pure
// routines; no character templates, console identifiers, game or save data.
#include <assert.h>
#include <signal.h>
#include <sys/wait.h>
#include <unistd.h>
#include "../hle_mii.c"

module_t g_mod[MAX_MOD];
int g_nmod;
static unsigned default_calls, random_calls, conversion_calls, ctors, dtors;
static int reject_conversion, reject_helper, have_author;
static uint8_t first_author[16];

static void author_check(void) {
    uint8_t author[16];
    h_mii_GetDeviceId(author);
    assert((author[6] & 0xf0) == 0x40 && (author[8] & 0xc0) == 0x80);
    if (!have_author) { memcpy(first_author, author, 16); have_author = 1; }
    else assert(!memcmp(first_author, author, 16));
}
static void fixture_utility_ctor(mii_utility *utility) { memset(utility, 0xa5, sizeof *utility); ctors++; }
static void fixture_utility_dtor(mii_utility *utility) { assert(utility->words[0] == 0xa5a5a5a5a5a5a5a5ull); dtors++; }
static void fixture_default(mii_store_data *store, mii_utility *utility, int index) {
    assert(utility && index >= 0 && index < 6); author_check();
    memset(store, 0, sizeof *store); store->rest[0] = (uint8_t)index; default_calls++;
}
static void fixture_random(mii_store_data *store, mii_utility *utility, const mii_random_desc *description) {
    assert(utility && description->age == 3 && description->gender == 2 && description->face_color == 3);
    author_check(); memset(store, 0, sizeof *store); store->rest[0] = 0x70; random_calls++;
}
static void fixture_from_ver3(const void *legacy, mii_store_data *store, mii_utility *utility) {
    assert(legacy && utility); memset(store, 0, sizeof *store);
    store->rest[0] = reject_conversion ? 0xff : 0x71; conversion_calls++;
}
static void fixture_to_char(mii_char_info *out, const mii_store_data *store) {
    memset(out, 0, sizeof *out); out->bytes[0] = 0x31; out->bytes[1] = store->rest[0];
}
static int fixture_verify_char(const mii_char_info *info) { return info->bytes[0] != 0x31 || info->bytes[1] == 0xff; }
static int fixture_verify_ver3(const void *legacy) { return *(const uint32_t *)legacy != 0x12345678; }
void *module_sym(module_t *module, const char *name) {
    assert(module == &g_mod[1]);
    if (reject_helper) return NULL;
#define FIXTURE(symbol, function) if (!strcmp(name, symbol)) return (void *)function
    FIXTURE("_ZN2nn3mii6detail11UtilityImplC1Ev", fixture_utility_ctor);
    FIXTURE("_ZN2nn3mii6detail11UtilityImplD1Ev", fixture_utility_dtor);
    FIXTURE("_ZN2nn3mii6detail12StoreDataRaw12BuildDefaultEPNS1_11UtilityImplEi", fixture_default);
    FIXTURE("_ZN2nn3mii6detail12StoreDataRaw11BuildRandomEPNS1_11UtilityImplERKNS0_10RandomDescE", fixture_random);
    FIXTURE("_ZNK2nn3mii6detail16Ver3StoreDataRaw16BuildToStoreDataEPNS1_12StoreDataRawEPNS1_11UtilityImplE", fixture_from_ver3);
    FIXTURE("_ZN2nn3mii6detail11CharInfoRaw19SetFromStoreDataRawERKNS1_12StoreDataRawE", fixture_to_char);
    FIXTURE("_ZNK2nn3mii6detail11CharInfoRaw6VerifyEv", fixture_verify_char);
    FIXTURE("_ZNK2nn3mii6detail16Ver3StoreDataRaw6VerifyEv", fixture_verify_ver3);
#undef FIXTURE
    return NULL;
}

int main(void) {
    g_nmod = 2;
    strcpy(g_mod[0].name, "main"); strcpy(g_mod[0].build_id, "21450c647b8c5940ed5b68218ea128fd");
    strcpy(g_mod[1].name, "sdk"); strcpy(g_mod[1].build_id, "5fd4f531c1195e9e5510c9e73f22cd39");
    mii_database database = {(void *)1}; h_mii_Ctor(&database); assert(!database.service);
    int count = 99;
    mii_char_info output[8]; memset(output, 0xce, sizeof output);
    assert(h_mii_Get(&database, &count, output, 8, 1) != RES_OK && count == 0);
    g_mod[1].build_id[0] = '0'; assert(h_mii_Initialize(&database) != RES_OK && !database.service);
    g_mod[1].build_id[0] = '5'; g_mod[0].build_id[0] = '0';
    assert(h_mii_Initialize(&database) != RES_OK && !database.service);
    g_mod[0].build_id[0] = '2';
    pid_t child = fork(); assert(child >= 0);
    if (!child) {
        reject_helper = 1;
        assert(h_mii_Initialize(&database) != RES_OK && !database.service && !default_calls);
        _exit(0);
    }
    int status; assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
    assert(h_mii_Initialize(&database) == RES_OK && database.service);
    assert(default_calls == 6 && ctors == dtors);
    assert(h_mii_Initialize(&database) == RES_OK && default_calls == 6);
    assert(h_mii_GetCount(&database, 0) == 0 && h_mii_GetCount(&database, 1) == 0);
    assert(h_mii_GetCount(&database, 2) == 6 && h_mii_GetCount(&database, 3) == 6);
    assert(!h_mii_IsUpdated(&database, 1) && !h_mii_IsUpdated(&database, 3));
    assert(h_mii_Get(&database, &count, output, 8, 1) == RES_OK && count == 0 && output[0].bytes[0] == 0xce);
    assert(h_mii_Get(&database, &count, output, 8, 3) == RES_OK && count == 6);
    for (int i = 0; i < count; ++i) assert(output[i].bytes[0] == 0x31 && output[i].bytes[1] == i);
    assert(output[6].bytes[0] == 0xce && output[7].bytes[0] == 0xce);
    assert(h_mii_Get(&database, &count, output, 2, 2) == RES_OK && count == 2);
    assert(h_mii_Get(&database, &count, NULL, 0, 2) == RES_OK && count == 0);
    assert(h_mii_Get(&database, &count, NULL, 1, 2) != RES_OK && count == 0);
    assert(h_mii_Get(&database, &count, output, -1, 1) != RES_OK && count == 0);
    assert(h_mii_Get(&database, &count, output, 8, 4) != RES_OK && count == 0);
    h_mii_BuildDefault(&database, output, 5); assert(output[0].bytes[1] == 5 && default_calls == 7);
    mii_random_desc description = {3, 2, 3};
    h_mii_BuildRandom(&database, output, &description); assert(output[0].bytes[1] == 0x70 && random_calls == 1);
    uint32_t legacy = 0; mii_char_info before = output[0];
    assert(h_mii_Convert(&database, output, &legacy) != RES_OK && conversion_calls == 0);
    assert(!memcmp(&before, output, sizeof before));
    legacy = 0x12345678; reject_conversion = 1;
    assert(h_mii_Convert(&database, output, &legacy) != RES_OK && conversion_calls == 1);
    assert(!memcmp(&before, output, sizeof before));
    reject_conversion = 0;
    assert(h_mii_Convert(&database, output, &legacy) == RES_OK && output[0].bytes[1] == 0x71 && conversion_calls == 2);
    assert(ctors == dtors);
    int index = 10; assert(h_mii_AppendMii(&index) == 0xe7e && index == -1);
    assert(h_mii_AppendMii(NULL) == 0xe7e);
    child = fork(); assert(child >= 0);
    if (!child) { h_mii_BuildDefault(&database, output, 6); _exit(1); }
    assert(waitpid(child, &status, 0) == child && WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
    h_mii_Dtor(&database); assert(!database.service);
    assert(h_mii_Convert(&database, output, &legacy) != RES_OK);
    puts("mii: build gates, empty user database, six SDK defaults, validated helper dispatch, failure atomicity and editor cancellation passed");
    return 0;
}
