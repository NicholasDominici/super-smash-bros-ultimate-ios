// nn::ro: static-only titles keep lookup-by-name/failing-load behavior. The
// inspected Smash ABI loads only exact cataloged images with an active NRR.
// Runtime code comes from already-rewritten/signed pages, never input buffers.
#include "hle.h"
#include <CommonCrypto/CommonDigest.h>
#define RO_FAIL ((Result)(22 | (1 << 9)))
#define RO_BAD_NRO ((Result)0x816)
#define RO_NOT_FOUND ((Result)0xa16)
#define RO_BAD_NRR ((Result)0xc16)
enum { RO_MODULES = 512, RO_REGISTRATIONS = 64 };

// SDK 5fd4f531... Module fields: LoadModuleInternal +0x34759c..+0x347690.
// RegistrationInfo fields: RegisterModuleInfo +0x347298..+0x3472b4.
typedef struct { void *module; uint32_t loaded, reserved; const void *image; void *bss; } ro_module_abi;
typedef struct { uint32_t registered, reserved; const void *image; void *prev, *next; } ro_registration_abi;
_Static_assert(sizeof(ro_module_abi) == 0x20, "SDK Module ABI");
_Static_assert(sizeof(ro_registration_abi) == 0x20, "SDK RegistrationInfo ABI");
typedef struct { void *guest; module_t *module; unsigned loading; } ro_module_record;
typedef struct { void *guest; unsigned count; uint8_t *hashes; } ro_registration;
static ro_module_record modules[RO_MODULES];
static ro_registration registrations[RO_REGISTRATIONS];
static unsigned finalizing;

static uint32_t read32(const void *p) { uint32_t n; memcpy(&n, p, 4); return n; }
static uint64_t read64(const void *p) { uint64_t n; memcpy(&n, p, 8); return n; }
static ro_module_record *module_record(const void *guest) {
    for (unsigned i = 0; i < RO_MODULES; i++) if (modules[i].guest == guest) return &modules[i];
    return NULL;
}
static int registered_hash(const uint8_t hash[32]) {
    for (unsigned i = 0; i < RO_REGISTRATIONS; i++) {
        const ro_registration *r = &registrations[i];
        for (unsigned j = 0; r->guest && j < r->count; j++)
            if (!memcmp(r->hashes + j * 32, hash, 32)) return 1;
    }
    return 0;
}
HLE_FORCE("_ZN2nn2ro10InitializeEv", "native catalog adapter; no ldr:ro session", Result, h_ro_Initialize, void) {
    LOG("init takeover: ro::Initialize (%s)", dm_nro_enabled() ? "signed NRO catalog" : "static modules only");
    return 0;
}
HLE_FORCE("_ZN2nn2ro12LookupSymbolEPmPKc", "find a symbol in active native modules", Result, h_ro_LookupSymbol, uintptr_t *out, const char *name) {
    if (!out || !name) return RO_NOT_FOUND;
    dm_nro_lock(); void *p = guest_sym(name);
    if (p) *out = (uintptr_t)p;
    dm_nro_unlock(); return p ? RES_OK : RO_NOT_FOUND;
}
HLE_FORCE("_ZN2nn2ro18LookupModuleSymbolEPmPKNS0_6ModuleEPKc", "look up only the requested native NRO", Result, h_ro_LookupModuleSymbol, uintptr_t *out, const void *guest, const char *name) {
    if (!out || !guest || !name) return RO_NOT_FOUND;
    dm_nro_lock(); ro_module_record *record = module_record(guest);
    void *p = record && !record->loading && record->module->active ? module_sym(record->module, name) : NULL;
    if (p) *out = (uintptr_t)p;
    dm_nro_unlock(); return p ? RES_OK : RO_NOT_FOUND;
}
HLE_FORCE("_ZN2nn2ro13GetBufferSizeEPmPKv", "NRO BSS size from exact original-byte catalog identity", Result, h_ro_GetBufferSize, size_t *out, const void *image) {
    if (!out) return RO_BAD_NRO;
    *out = 0;
    if (!dm_nro_enabled() || !image) return RO_FAIL;
    const dm_nro_catalog_entry *entry = dm_nro_identify(image);
    if (!entry) return RO_BAD_NRO;
    *out = entry->bss_size; return RES_OK;
}
HLE_FORCE("_ZN2nn2ro10LoadModuleEPNS0_6ModuleEPKvPvmi", "load exact registered NRO from signed rewritten pages", Result, h_ro_LoadModule, void *guest, const void *image, void *bss, size_t size, int flag) {
    if (!dm_nro_enabled() || !guest || !image || flag < 0 || flag > 3) return RO_FAIL;
    const dm_nro_catalog_entry *entry = dm_nro_identify(image);
    if (!entry || size < entry->bss_size || (entry->bss_size && !bss)) return RO_BAD_NRO;
    dm_nro_lock();
    if (finalizing || module_record(guest) || !registered_hash(entry->sha256)) { dm_nro_unlock(); return RO_FAIL; }
    ro_module_record *record = NULL;
    for (unsigned i = 0; i < RO_MODULES; i++) if (!modules[i].guest) { record = &modules[i]; break; }
    if (!record) { dm_nro_unlock(); return RO_FAIL; }
    // DT_INIT may recursively load another NRO. Reserve this public object's
    // record before entering guest code so the nested load cannot reuse it.
    *record = (ro_module_record){guest, NULL, 1};
    module_t *m = dm_nro_load(entry);
    if (!m) { memset(record, 0, sizeof *record); dm_nro_unlock(); return RO_FAIL; }
    ro_module_abi value = {m->nro_sdk_object, 1, 0, image, bss};
    memcpy(guest, &value, sizeof value); *record = (ro_module_record){guest, m, 0};
    if (!dm_nro_commit(m)) {
        memset(record, 0, sizeof *record); ((ro_module_abi *)guest)->loaded = 0;
        dm_nro_unload(m); dm_nro_unlock(); return RO_FAIL;
    }
    dm_nro_unlock(); return RES_OK;
}
HLE_FORCE("_ZN2nn2ro10LoadModuleEPNS0_6ModuleEPKvPvmib", "SDK19 compatibility form remains gated by inspected SDK ABI", Result, h_ro_LoadModule2, void *m, const void *image, void *buf, size_t size, int flag, unsigned b) {
    if (b & 255) return RO_FAIL;
    return h_ro_LoadModule(m, image, buf, size, flag);
}
HLE_FORCE("_ZN2nn2ro12UnloadModuleEPNS0_6ModuleE", "fini and retire one native NRO with dependency lifetime retention", void, h_ro_UnloadModule, void *guest) {
    if (!guest) return;
    dm_nro_lock(); ro_module_record *record = module_record(guest);
    if (record && !record->loading) {
        module_t *m = record->module; memset(record, 0, sizeof *record);
        dm_nro_unload(m); ((ro_module_abi *)guest)->loaded = 0;
    }
    dm_nro_unlock();
}
HLE_FORCE("_ZN2nn2ro18RegisterModuleInfoEPNS0_16RegistrationInfoEPKv", "register exact signed-build NRR original NRO hashes", Result, h_ro_RegisterModuleInfo, void *guest, const void *image) {
    if (!dm_nro_enabled() || !guest || !image || memcmp(image, "NRR0", 4)) return RO_BAD_NRR;
    const uint8_t *bytes = image;
    uint32_t size = read32(bytes + 0x338), offset = read32(bytes + 0x340), count = read32(bytes + 0x344);
    if (size < 0x350 || size > 16u * 1024 * 1024 || offset < 0x350 || offset > size ||
        count > (size - offset) / 32 || read64(bytes + 0x330) != 0x01006a800016e000ull) return RO_BAD_NRR;
    uint8_t hash[32]; CC_SHA256(image, size, hash); int allowed = 0;
    for (unsigned i = 0; i < dm_nrr_catalog_count; i++)
        allowed |= dm_nrr_catalog[i].image_size == size && !memcmp(hash, dm_nrr_catalog[i].sha256, 32);
    if (!allowed) return RO_BAD_NRR;
    dm_nro_lock(); ro_registration *record = NULL;
    for (unsigned i = 0; i < RO_REGISTRATIONS; i++) {
        if (registrations[i].guest == guest) { dm_nro_unlock(); return RO_FAIL; }
        if (!record && !registrations[i].guest) record = &registrations[i];
    }
    if (!record || finalizing) { dm_nro_unlock(); return RO_FAIL; }
    uint8_t *hashes = malloc(count ? (size_t)count * 32 : 1);
    if (!hashes) { dm_nro_unlock(); return RO_FAIL; }
    memcpy(hashes, bytes + offset, (size_t)count * 32); *record = (ro_registration){guest, count, hashes};
    ro_registration_abi value = {1, 0, image, (uint8_t *)guest + 0x10, (uint8_t *)guest + 0x10};
    memcpy(guest, &value, sizeof value); dm_nro_unlock(); return RES_OK;
}
HLE_FORCE("_ZN2nn2ro20UnregisterModuleInfoEPNS0_16RegistrationInfoE", "remove one NRR grant without disturbing loaded modules", void, h_ro_UnregisterModuleInfo, void *guest) {
    if (!guest) return;
    dm_nro_lock();
    for (unsigned i = 0; i < RO_REGISTRATIONS; i++) if (registrations[i].guest == guest) {
        free(registrations[i].hashes); memset(&registrations[i], 0, sizeof registrations[i]);
        ((ro_registration_abi *)guest)->registered = 0; break;
    }
    dm_nro_unlock();
}
HLE_FORCE("_ZN2nn2ro8FinalizeEv", "close native modules and NRRs in reverse load order", void, h_ro_Finalize, void) {
    dm_nro_lock();
    // A constructor cannot finalize its own still-pending load. In particular,
    // do not clear another recursive load's reservation or dereference it.
    for (unsigned i = 0; i < RO_MODULES; i++) if (modules[i].loading) {
        LOG("ro::Finalize not performed: NRO constructor is still running"); dm_nro_unlock(); return;
    }
    finalizing = 1;
    for (;;) {
        ro_module_record *last = NULL;
        for (unsigned i = 0; i < RO_MODULES; i++)
            if (modules[i].guest && (!last || modules[i].module->load_serial > last->module->load_serial)) last = &modules[i];
        if (!last) break;
        h_ro_UnloadModule(last->guest);
    }
    for (unsigned i = 0; i < RO_REGISTRATIONS; i++) if (registrations[i].guest) h_ro_UnregisterModuleInfo(registrations[i].guest);
    finalizing = 0; dm_nro_unlock();
}
