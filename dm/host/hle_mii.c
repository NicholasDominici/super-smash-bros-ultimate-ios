// Local Mii service for Smash 13.0.5. Character templates and conversion code
// remain in the user's signed SDK; no console database or Mii editor is present.
#include "hle.h"

#if DM_GAME_PROGRAM_ID == 0x01006A800016E000ull

enum { MII_SOURCE_DATABASE = 1, MII_SOURCE_DEFAULT = 2, MII_DEFAULT_COUNT = 6 };
typedef struct { uint8_t bytes[0x58]; } mii_char_info;
typedef struct { uint64_t alignment; uint8_t rest[0x3c]; } mii_store_data;
typedef struct { uint64_t words[2]; } mii_utility;
typedef struct { int age, gender, face_color; } mii_random_desc;
typedef struct { void *service; } mii_database;
_Static_assert(sizeof(mii_char_info) == 0x58, "SDK CharInfo size");
_Static_assert(sizeof(mii_store_data) == 0x48, "aligned StoreData workspace");
_Static_assert(sizeof(mii_utility) == 0x10, "SDK UtilityImpl size");
_Static_assert(sizeof(mii_database) == 8, "SDK Database size");

// Layouts/call signatures were checked against sdk 5fd4f531... exports. This
// gate covers those ABI assumptions even though no fixed code offsets are used.
static module_t *mii_sdk(void) {
    if (strcmp(dm_main_build(), "21450c647b8c5940ed5b68218ea128fd")) return NULL;
    for (int i = 0; i < g_nmod; ++i)
        if (!strcmp(g_mod[i].name, "sdk") &&
            !strcmp(g_mod[i].build_id, "5fd4f531c1195e9e5510c9e73f22cd39")) return &g_mod[i];
    return NULL;
}

typedef struct {
    void (*utility_ctor)(mii_utility *);
    void (*utility_dtor)(mii_utility *);
    void (*build_default)(mii_store_data *, mii_utility *, int);
    void (*build_random)(mii_store_data *, mii_utility *, const mii_random_desc *);
    void (*from_ver3)(const void *, mii_store_data *, mii_utility *);
    void (*to_char)(mii_char_info *, const mii_store_data *);
    int (*verify_char)(const mii_char_info *);
    int (*verify_ver3)(const void *);
} mii_sdk_helpers;
static mii_sdk_helpers mii_helpers;
static mii_char_info mii_defaults[MII_DEFAULT_COUNT];
static pthread_once_t mii_helpers_once = PTHREAD_ONCE_INIT;
static int mii_helpers_ready;
static char mii_local_service;

static void *mii_symbol(module_t *sdk, const char *name) {
    void *fn = module_sym(sdk, name);
    if (!fn) LOG("mii: required SDK helper unavailable: %s", name);
    return fn;
}

static void mii_check_char(const mii_char_info *info) {
    int error = mii_helpers.verify_char(info);
    if (error) die("mii: original SDK rejected generated CharInfo (verification %d)", error);
}

static void mii_make_default(mii_char_info *out, int index) {
    mii_utility utility;
    mii_store_data store = {0};
    mii_helpers.utility_ctor(&utility);
    mii_helpers.build_default(&store, &utility, index);
    mii_helpers.to_char(out, &store);
    mii_helpers.utility_dtor(&utility);
    mii_check_char(out);
}

static void mii_resolve_helpers(void) {
    module_t *sdk = mii_sdk();
    if (!sdk) return;
#define MII_HELPER(field, symbol) mii_helpers.field = mii_symbol(sdk, symbol); if (!mii_helpers.field) return
    MII_HELPER(utility_ctor, "_ZN2nn3mii6detail11UtilityImplC1Ev");
    MII_HELPER(utility_dtor, "_ZN2nn3mii6detail11UtilityImplD1Ev");
    MII_HELPER(build_default, "_ZN2nn3mii6detail12StoreDataRaw12BuildDefaultEPNS1_11UtilityImplEi");
    MII_HELPER(build_random, "_ZN2nn3mii6detail12StoreDataRaw11BuildRandomEPNS1_11UtilityImplERKNS0_10RandomDescE");
    MII_HELPER(from_ver3, "_ZNK2nn3mii6detail16Ver3StoreDataRaw16BuildToStoreDataEPNS1_12StoreDataRawEPNS1_11UtilityImplE");
    MII_HELPER(to_char, "_ZN2nn3mii6detail11CharInfoRaw19SetFromStoreDataRawERKNS1_12StoreDataRawE");
    MII_HELPER(verify_char, "_ZNK2nn3mii6detail11CharInfoRaw6VerifyEv");
    MII_HELPER(verify_ver3, "_ZNK2nn3mii6detail16Ver3StoreDataRaw6VerifyEv");
#undef MII_HELPER
    for (int i = 0; i < MII_DEFAULT_COUNT; ++i) mii_make_default(&mii_defaults[i], i);
    mii_helpers_ready = 1;
    LOG("mii: local database initialized (0 user Miis, %d SDK defaults)", MII_DEFAULT_COUNT);
}

static int mii_is_initialized(const mii_database *database) {
    return database && database->service == &mii_local_service && mii_sdk() && mii_helpers_ready;
}
static int mii_source_valid(int source) { return source >= 0 && !(source & ~3); }

// StoreData helpers obtain the author's identity solely to calculate their
// temporary device CRC. Use a distinct process-local UUID, never a fabricated
// console identifier. These temporary StoreData records are not persisted or
// exposed: the caller receives a CharInfo containing no author/device CRC.
static pthread_once_t mii_author_once = PTHREAD_ONCE_INIT;
static uint8_t mii_author_uuid[16];
static void mii_author_init(void) {
    arc4random_buf(mii_author_uuid, sizeof mii_author_uuid);
    mii_author_uuid[6] = (mii_author_uuid[6] & 15) | 0x40;
    mii_author_uuid[8] = (mii_author_uuid[8] & 63) | 0x80;
}
HLE_FORCE("_ZN2nn3mii6detail11GetDeviceIdEPNS1_8DeviceIdE",
          "Mii-only settings service boundary: process-local author UUID for temporary StoreData CRCs",
          void, h_mii_GetDeviceId, void *out) {
    if (!out || !mii_sdk()) die("mii: unsupported author identity ABI");
    pthread_once(&mii_author_once, mii_author_init);
    memcpy(out, mii_author_uuid, sizeof mii_author_uuid);
}

HLE_FORCE("_ZN2nn3mii8DatabaseC1Ev", "local Mii service object construction", void, h_mii_Ctor, mii_database *database) {
    database->service = NULL;
}
HLE_FORCE("_ZN2nn3mii8DatabaseD1Ev", "local Mii service object destruction", void, h_mii_Dtor, mii_database *database) {
    database->service = NULL;
}
HLE_FORCE("_ZN2nn3mii8Database10InitializeEv", "local Mii database service with an empty user database", Result, h_mii_Initialize, mii_database *database) {
    if (!database || !mii_sdk()) return RES_FAIL;
    pthread_once(&mii_helpers_once, mii_resolve_helpers);
    if (!mii_helpers_ready) return RES_FAIL;
    database->service = &mii_local_service;
    return RES_OK;
}
HLE_FORCE("_ZN2nn3mii8Database9IsUpdatedEi", "immutable local Mii user/default sources", int, h_mii_IsUpdated, const mii_database *database, int source) {
    if (!mii_is_initialized(database) || !mii_source_valid(source)) die("mii: IsUpdated requires an initialized database and valid source flags");
    return 0;
}
HLE_FORCE("_ZNK2nn3mii8Database8GetCountEi", "count empty user source and the six SDK default Miis separately", int, h_mii_GetCount, const mii_database *database, int source) {
    if (!mii_is_initialized(database) || !mii_source_valid(source)) die("mii: GetCount requires an initialized database and valid source flags");
    return source & MII_SOURCE_DEFAULT ? MII_DEFAULT_COUNT : 0;
}
HLE_FORCE("_ZN2nn3mii8Database3GetEPiPNS0_8CharInfoEii", "enumerate genuine SDK defaults; no user database records are invented", Result, h_mii_Get,
          const mii_database *database, int *count, mii_char_info *out, int capacity, int source) {
    if (!count) return RES_FAIL;
    *count = 0;
    if (!mii_is_initialized(database) || !mii_source_valid(source) || capacity < 0 || (capacity && !out)) return RES_FAIL;
    int n = source & MII_SOURCE_DEFAULT ? MII_DEFAULT_COUNT : 0;
    if (n > capacity) n = capacity;
    if (n) memcpy(out, mii_defaults, (size_t)n * sizeof *out);
    *count = n;
    return RES_OK;
}
HLE_FORCE("_ZNK2nn3mii8Database12BuildDefaultEPNS0_8CharInfoEi", "build a default Mii using the original signed SDK templates and validator", void, h_mii_BuildDefault,
          const mii_database *database, mii_char_info *out, int index) {
    if (!mii_is_initialized(database) || !out || index < 0 || index >= MII_DEFAULT_COUNT) die("mii: invalid BuildDefault arguments");
    mii_make_default(out, index);
}
HLE_FORCE("_ZN2nn3mii8Database11BuildRandomEPNS0_8CharInfoERKNS0_10RandomDescE", "generate a valid random Mii through the original signed SDK generator", void, h_mii_BuildRandom,
          const mii_database *database, mii_char_info *out, const mii_random_desc *description) {
    if (!mii_is_initialized(database) || !out || !description ||
        description->age < 0 || description->age > 3 || description->gender < 0 || description->gender > 2 ||
        description->face_color < 0 || description->face_color > 3) die("mii: invalid BuildRandom arguments");
    mii_utility utility;
    mii_store_data store = {0};
    mii_helpers.utility_ctor(&utility);
    mii_helpers.build_random(&store, &utility, description);
    mii_helpers.to_char(out, &store);
    mii_helpers.utility_dtor(&utility);
    mii_check_char(out);
}
HLE_FORCE("_ZN2nn3mii8Database7ConvertEPNS0_8CharInfoERKNS0_13Ver3StoreDataE", "validate and convert a legacy Mii using the original signed SDK", Result, h_mii_Convert,
          const mii_database *database, mii_char_info *out, const void *legacy) {
    if (!mii_is_initialized(database) || !out || !legacy || mii_helpers.verify_ver3(legacy)) return RES_FAIL;
    mii_utility utility;
    mii_store_data store = {0};
    mii_char_info converted;
    mii_helpers.utility_ctor(&utility);
    mii_helpers.from_ver3(legacy, &store, &utility);
    mii_helpers.to_char(&converted, &store);
    mii_helpers.utility_dtor(&utility);
    if (mii_helpers.verify_char(&converted)) return RES_FAIL;
    memcpy(out, &converted, sizeof converted);
    return RES_OK;
}
HLE_FORCE("_ZN2nn3mii9AppendMiiEPi", "the console system Mii editor is unavailable; return its real cancellation result", Result, h_mii_AppendMii, int *index) {
    if (index) *index = -1;
    return 0xe7eu; // SDK AppletOutput::GetResult maps cancellation to this Result.
}

#endif
