// Synthetic original AArch64 images exercise the real native NRO mapping path.
// No game bytes or device/cloud access; loader internals are visible for setup.
#include <assert.h>
#include <stdatomic.h>
#include <time.h>
#include <sys/wait.h>
#include <mach/mach.h>
#include "../loader.c"
#include "../hle_ro.c"

struct dm_flags g_flag;
static unsigned init_calls, fini_calls, sdk_initializations, unmaps;
static uint64_t *static_a, *static_b, *static_abs;
static _Atomic uintptr_t initialized_targets[2][128];
static _Atomic unsigned initialized_counts[2];
static uintptr_t slot_value(const uint64_t *slot) { return atomic_load_explicit((const _Atomic uint64_t *)slot, memory_order_acquire); }
static void assert_withdrawn(void) {
    assert(slot_value(static_a) == (uintptr_t)nro_deferred_unavailable);
    assert(slot_value(static_b) == (uintptr_t)nro_deferred_unavailable);
    assert(slot_value(static_abs) == (uintptr_t)nro_deferred_unavailable);
}
static void premature_call_fails(uintptr_t target) {
    pid_t child = fork(); assert(child >= 0);
    if (!child) { freopen("/dev/null", "w", stderr); ((void (*)(void))target)(); _exit(0); }
    int status; waitpid(child, &status, 0); assert(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
}
static const void *recursive_image;
static ro_module_abi *recursive_outer, *recursive_child;
static void *recursive_bss;
static void fixture_init(void) {
    assert(sdk_initializations > init_calls); init_calls++;
    module_t *current = dynamic_provider((uintptr_t)__builtin_return_address(0)); assert(current && !current->committed);
    unsigned kind = module_sym(current, "test_value") ? 0 : 1;
    assert(slot_value(kind ? static_b : static_a) == (uintptr_t)nro_deferred_unavailable);
    if (recursive_image) {
        const void *image = recursive_image; recursive_image = NULL;
        assert(module_record(recursive_outer) && module_record(recursive_outer)->loading);
        assert(h_ro_LoadModule(recursive_outer, image, recursive_bss, 0x1000, 0) != 0);
        uintptr_t symbol = 0;
        assert(h_ro_LookupModuleSymbol(&symbol, recursive_outer, "test_value") != 0);
        h_ro_UnloadModule(recursive_outer); h_ro_Finalize();
        assert(module_record(recursive_outer) && module_record(recursive_outer)->loading);
        assert(h_ro_LoadModule(recursive_child, image, recursive_bss, 0x1000, 0) == 0);
        assert(recursive_child->loaded && !recursive_outer->loaded);
        assert(slot_value(static_a) == (uintptr_t)nro_deferred_unavailable);
        assert(slot_value(static_b) == (uintptr_t)module_sym(module_record(recursive_child)->module, "test_B"));
    }
    unsigned index = atomic_load(&initialized_counts[kind]); assert(index < 128);
    atomic_store(&initialized_targets[kind][index], (uintptr_t)module_sym(current, kind ? "test_B" : "test_value"));
    atomic_store_explicit(&initialized_counts[kind], index + 1, memory_order_release);
}
static void fixture_fini(void) {
    module_t *current = dynamic_provider((uintptr_t)__builtin_return_address(0)); assert(current && !current->committed);
    assert(slot_value(module_sym(current, "test_value") ? static_a : static_b) == (uintptr_t)nro_deferred_unavailable);
    fini_calls++;
}
uint64_t now_ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec; }
uint64_t guest_ns(void) { return now_ns(); }
void *hlecount_wrap(const char *kind, const char *name, void *fn) { (void)kind; (void)name; return fn; }
void hlecount_seal(void) {}
int hle_implements(const char *name) { return !strcmp(name, "SyntheticInit") || !strcmp(name, "SyntheticFini"); }
uint64_t resolve_import(module_t *m, const char *name) {
    (void)m;
    if (!strcmp(name, "SyntheticInit")) return (uint64_t)fixture_init;
    if (!strcmp(name, "SyntheticFini")) return (uint64_t)fixture_fini;
    return 0;
}
void gate_register(uint64_t address, const char *kind, int argument, uint64_t original) { (void)address; (void)kind; (void)argument; (void)original; }
void gate_unregister_range(uint64_t start, uint64_t size) { assert(start && size); unmaps++; }

static void sdk_initialize_fixture(void *object, uintptr_t base, size_t size, const Elf64_Dyn *dynamic, unsigned manual) {
    assert(object && base && size && dynamic && !manual);
    assert(((void **)object)[0] == object && ((void **)object)[1] == object);
    memcpy((uint8_t *)object + 0x20, &base, 8);
    sdk_initializations++;
}
static void *read_file(const char *directory, const char *name) {
    char path[2048]; snprintf(path, sizeof path, "%s/%s", directory, name);
    FILE *f = fopen(path, "rb"); assert(f);
    fseek(f, 0, SEEK_END); long size = ftell(f); rewind(f); assert(size > 0);
    void *data = malloc((size_t)size); assert(data);
    assert(fread(data, 1, (size_t)size, f) == (size_t)size); fclose(f); return data;
}
static void *read_path(const char *path) {
    FILE *f = fopen(path, "rb"); assert(f);
    fseek(f, 0, SEEK_END); long size = ftell(f); rewind(f); assert(size > 0);
    void *data = malloc((size_t)size); assert(data);
    assert(fread(data, 1, (size_t)size, f) == (size_t)size); fclose(f); return data;
}
static _Atomic int reading = 1;
static _Atomic(uintptr_t) observed_address;
static void *reader(void *unused) {
    (void)unused;
    while (atomic_load(&reading)) {
        module_t *m = module_of((void *)atomic_load(&observed_address));
        if (m && m->dynamic) { assert(strlen(m->name) == 8); assert(m->base && m->size); }
        for (unsigned kind = 0; kind < 2; kind++) {
            uintptr_t value = slot_value(kind ? static_b : static_a);
            if (value == (uintptr_t)nro_deferred_unavailable) continue;
            unsigned count = atomic_load_explicit(&initialized_counts[kind], memory_order_acquire); int found = 0;
            for (unsigned i = 0; i < count; i++) found |= atomic_load(&initialized_targets[kind][i]) == value;
            assert(found);  // Only this provider's already-initialized generation may appear.
        }
    }
    return NULL;
}
static vm_prot_t protections(uintptr_t pointer) {
    vm_address_t address = pointer; vm_size_t size = 0; mach_port_t object = MACH_PORT_NULL;
    vm_region_basic_info_data_64_t info;
    mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
    assert(vm_region_64(mach_task_self(), &address, &size, VM_REGION_BASIC_INFO_64,
                        (vm_region_info_t)&info, &count, &object) == KERN_SUCCESS);
    if (object != MACH_PORT_NULL) mach_port_deallocate(mach_task_self(), object);
    assert(pointer >= address && pointer - address < size);
    return info.protection;
}

int main(int argc, char **argv) {
    assert(argc == 4 && dm_nro_catalog_count == 2);
    strlcpy(g_module_dir, argv[1], sizeof g_module_dir);
    g_nmod = g_static_nmod = 2;
    strcpy(g_mod[0].name, "main"); strcpy(g_mod[0].build_id, "21450c647b8c5940ed5b68218ea128fd");
    g_mod[0].base = calloc(1, 4096); g_mod[0].size = 4096;
    strcpy(g_mod[1].name, "sdk"); strcpy(g_mod[1].build_id, "5fd4f531c1195e9e5510c9e73f22cd39");
    g_mod[1].base = (uint8_t *)((uintptr_t)sdk_initialize_fixture & ~(uintptr_t)0x3fff); g_mod[1].size = 0x4000;
    static const char sdk_names[] = "\0_ZN2nn2ro6detail8RoModule10InitializeEmmPKNS1_3Elf5Elf643DynEb";
    static Elf64_Sym sdk_symbols[2];
    sdk_symbols[1] = (Elf64_Sym){1, 0x12, 0, 1, (uintptr_t)sdk_initialize_fixture - (uintptr_t)g_mod[1].base, 0};
    g_mod[1].symtab = sdk_symbols; g_mod[1].strtab = sdk_names; g_mod[1].nsym = 2;
    create_keys(); force_init();
    assert(dm_nro_enabled());
    static const char main_names[] = "\0test_value\0test_B";
    static Elf64_Sym main_symbols[] = {{0}, {1, 0x12, 0, 0, 0, 0}, {12, 0x12, 0, 0, 0, 0}};
    static const Elf64_Dyn main_dynamic[] = {{DT_RELA, {.d_ptr = 0x200}}, {DT_RELASZ, {.d_val = 72}}, {0}};
    g_mod[0].symtab = main_symbols; g_mod[0].strtab = main_names; g_mod[0].nsym = 3; g_mod[0].dyn = main_dynamic; g_mod[0].data_off = 0x800;
    Elf64_Rela *main_relocs = (Elf64_Rela *)(g_mod[0].base + 0x200);
    main_relocs[0] = (Elf64_Rela){0x800, (1ull << 32) | R_AARCH64_GLOB_DAT, 0};
    main_relocs[1] = (Elf64_Rela){0x808, (2ull << 32) | R_AARCH64_JUMP_SLOT, 0};
    main_relocs[2] = (Elf64_Rela){0x810, (1ull << 32) | R_AARCH64_ABS64, 0};
    static_a = (uint64_t *)(g_mod[0].base + 0x800); static_b = static_a + 1; static_abs = static_a + 2;
    assert(relocate(&g_mod[0]) && g_nro_deferred_count == 3); assert_withdrawn();
    premature_call_fails(slot_value(static_a));
    uint8_t *a = read_file(argv[2], "0.nro"), *b = read_file(argv[2], "1.nro");
    void *nrr = read_path(argv[3]);
    ro_registration_abi grant = {0}; ro_module_abi ma = {0}, mb = {0}, duplicate = {0};
    size_t required = 99;
    assert(h_ro_GetBufferSize(&required, a) == 0 && required == 0x1000);
    char saved = g_mod[1].build_id[0]; g_mod[1].build_id[0] = '0';
    assert(h_ro_GetBufferSize(&required, a) != 0 && required == 0); g_mod[1].build_id[0] = saved;
    a[0x100] ^= 1; assert(h_ro_GetBufferSize(&required, a) != 0); a[0x100] ^= 1;
    void *bss = calloc(1, 0x1000); assert(bss);
    assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 0) != 0 && init_calls == 0);
    assert(h_ro_RegisterModuleInfo(&grant, nrr) == 0 && grant.registered == 1);
    assert(h_ro_RegisterModuleInfo(&grant, nrr) != 0);
    assert(h_ro_LoadModule(&ma, a, bss, 0x800, 0) != 0);
    assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 4) != 0);
    assert(guest_sym("test_value") == NULL && dm_nro_memory_bytes(0) == 0);
    assert(h_ro_LoadModule(&mb, b, bss, 0x1000, 0) != 0);  // provider not loaded: strict relocation must roll back.
    assert_withdrawn(); assert(!module_record(&mb) && dm_nro_memory_bytes(0) == 0 && init_calls == 0);
    g_mod[1].nsym = 0;
    assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 0) != 0);  // metadata helper absent: no publication or constructor.
    g_mod[1].nsym = 2;
    assert_withdrawn(); assert(!module_record(&ma) && dm_nro_memory_bytes(0) == 0 && init_calls == 0);
    const dm_nro_export_entry *admitted_export = g_nro_deferred[0].export;
    dm_nro_export_entry wrong_offset = *admitted_export; wrong_offset.offset += 4;
    g_nro_deferred[0].export = &wrong_offset;
    assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 0) != 0);
    g_nro_deferred[0].export = admitted_export;
    assert_withdrawn(); assert(!module_record(&ma) && dm_nro_memory_bytes(0) == 0 && init_calls == 0);
    unsigned failed_unmaps = unmaps; assert(failed_unmaps == 3);
    assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 0) == 0 && ma.loaded && init_calls == 1);
    assert(slot_value(static_a) == (uintptr_t)module_sym(module_record(&ma)->module, "test_value"));
    assert(slot_value(static_abs) == slot_value(static_a) && ((int (*)(void))slot_value(static_a))() == 42);
    assert(slot_value(static_b) == (uintptr_t)nro_deferred_unavailable);
    assert(h_ro_LoadModule(&duplicate, a, bss, 0x1000, 0) != 0 && init_calls == 1);
    assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 0) != 0);
    uintptr_t fn = 0;
    assert(h_ro_LookupModuleSymbol(&fn, &ma, "test_value") == 0 && fn);
    assert(((int (*)(void))fn)() == 42);
    module_t *snapshot = module_of((void *)fn); assert(snapshot && snapshot->dynamic && strlen(snapshot->name) == 8);
    uintptr_t old_base = (uintptr_t)snapshot->base; char old_name[16]; strcpy(old_name, snapshot->name);
    assert((protections(fn) & (VM_PROT_READ | VM_PROT_WRITE | VM_PROT_EXECUTE)) == (VM_PROT_READ | VM_PROT_EXECUTE));
    assert((protections(old_base + 0x8000) & (VM_PROT_READ | VM_PROT_WRITE | VM_PROT_EXECUTE)) == (VM_PROT_READ | VM_PROT_WRITE));
    assert(read64((uint8_t *)ma.module + 0x20) == old_base);
    assert(g_nmod == 2 && dm_nro_memory_bytes(0) > 0);
    h_ro_UnregisterModuleInfo(&grant); assert(!grant.registered && ((int (*)(void))fn)() == 42);
    h_ro_UnloadModule(&ma); assert(!ma.loaded && fini_calls == 1 && !guest_sym("test_value"));
    assert_withdrawn(); premature_call_fails(slot_value(static_a));
    assert(!module_of((void *)fn) && snapshot->base == (uint8_t *)old_base && !strcmp(snapshot->name, old_name));
    assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 0) != 0);
    assert(h_ro_RegisterModuleInfo(&grant, nrr) == 0);
    assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 0) == 0);
    assert(h_ro_LoadModule(&mb, b, bss, 0x1000, 0) == 0);
    uintptr_t provider = (uintptr_t)guest_sym("provider"), dependent = (uintptr_t)guest_sym("test_B");
    assert(provider && dependent && ((int (*)(void))dependent)() == 42);
    assert(slot_value(static_a) == (uintptr_t)module_sym(module_record(&ma)->module, "test_value"));
    assert(slot_value(static_b) == dependent);
    assert(!nro_deferred_target(module_record(&mb)->module, nro_export_find("test_value")));
    h_ro_UnloadModule(&ma);
    assert(slot_value(static_a) == (uintptr_t)nro_deferred_unavailable && slot_value(static_b) == dependent);
    assert(h_ro_LoadModule(&duplicate, a, bss, 0x1000, 0) != 0);  // retired provider is still held by B.
    assert(slot_value(static_a) == (uintptr_t)nro_deferred_unavailable);
    assert(!guest_sym("provider") && module_of((void *)provider));  // dependent retains native binding
    assert(((int (*)(void))dependent)() == 42);
    h_ro_UnloadModule(&mb); assert(!module_of((void *)provider) && !module_of((void *)dependent));
    assert(dm_nro_memory_bytes(0) == 0 && g_nmod == 2);
    recursive_image = b; recursive_outer = &ma; recursive_child = &mb; recursive_bss = bss;
    assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 0) == 0);
    assert(ma.loaded && mb.loaded && module_record(&ma) && module_record(&mb));
    assert(h_ro_LookupModuleSymbol(&fn, &mb, "test_B") == 0 && ((int (*)(void))fn)() == 42);
    h_ro_UnloadModule(&ma); h_ro_UnloadModule(&mb);
    assert(dm_nro_memory_bytes(0) == 0);
    pthread_t thread; assert(!pthread_create(&thread, NULL, reader, NULL));
    for (int i = 0; i < 40; i++) {
        assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 0) == 0);
        atomic_store(&observed_address, (uintptr_t)guest_sym("test_value"));
        h_ro_UnloadModule(&ma); assert(g_nmod == 2);
    }
    atomic_store(&reading, 0); pthread_join(thread, NULL);
    assert(h_ro_LoadModule(&ma, a, bss, 0x1000, 0) == 0);
    h_ro_Finalize();
    assert(!ma.loaded && !grant.registered && !guest_sym("test_value") && dm_nro_memory_bytes(0) == 0);
    assert_withdrawn(); assert(init_calls == fini_calls && unmaps == init_calls + failed_unmaps);
    printf("PASS: NRO identity, NRR grant, recursive constructor visibility, deferred static GOT commit/withdrawal, failed-load rollback, exact provider, reload, dependency retention, concurrent atomic publication (%u generations)\n", init_calls);
    free(a); free(b); free(nrr); free(bss); free(g_mod[0].base);
    return 0;
}
