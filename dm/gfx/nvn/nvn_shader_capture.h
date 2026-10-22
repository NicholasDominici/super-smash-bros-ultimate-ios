// Bounded, serialized capture of original NVN shader bytes. Private diagnostics
// only: no replacement shaders, key aliases, or claims about unvisited gameplay.
#pragma once
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define NVN_CAPTURE_SLOTS 131072u
#define NVN_CAPTURE_MAX_UNIQUE 65536u
#define NVN_CAPTURE_MAX_EVENTS 262144u
#define NVN_CAPTURE_MAX_BYTES (UINT64_C(1) << 30)
#define NVN_CAPTURE_MAX_LEDGER (UINT64_C(64) << 20)
#define NVN_CAPTURE_LEDGER "registration-census.jsonl"
#ifndef NVN_CAPTURE_LOG
#define NVN_CAPTURE_LOG(...) fprintf(stderr, __VA_ARGS__)
#endif

typedef struct {
    uint64_t programs, expected_stages, register_stages, mapped_stages;
    uint64_t deferred_stages, invalid_stages, draw_stages, captured_unique;
    uint64_t duplicates, unresolved_deferred, failures, bytes_written;
} nvn_capture_totals;
typedef struct { uint8_t digest[32]; uint32_t control_bytes, code_bytes; int used; } nvn_capture_key;
typedef struct { uint64_t serial; unsigned index; int used, deferred; } nvn_capture_pending;
typedef struct {
    pthread_mutex_t mutex;
    int initialized, active, registration, directory, ledger, broken;
    uint64_t sequence, ledger_bytes;
    nvn_capture_totals totals;
    nvn_capture_key *keys;
    nvn_capture_pending *pending;
} nvn_capture_state;
#define NVN_CAPTURE_INITIALIZER { .mutex = PTHREAD_MUTEX_INITIALIZER, .directory = -1, .ledger = -1 }

static uint32_t nvn_capture_u32(const void *p) { uint32_t v; memcpy(&v, p, 4); return v; }
// These are the exact shader_split/keys_hash boundaries. A caller must provide
// readable control bytes for this prefix and prove the complete code is mapped.
static int nvn_capture_lengths(const void *control, uint32_t *nctl, uint32_t *ncode) {
    if (!control || nvn_capture_u32(control) != UINT32_C(0x98761234)) return 0;
    const uint8_t *c = control;
    uint32_t own = nvn_capture_u32(c + 0x20);
    if (own < 0x760 || own > (64u << 20) || (own & 3)) return 0;
    *nctl = own < 0x880 ? own : 0x880;
    *ncode = nvn_capture_u32(c + 0x704);
    return *ncode && *ncode < (1u << 24) && nvn_capture_u32(c + 0x700) <= *ncode;
}
static int nvn_capture_code_valid(const void *control, const void *code, uint32_t ncode) {
    if (!code || ncode < 4) return 0;
    uint32_t magic = nvn_capture_u32(code);
    if (magic == UINT32_C(0x12345678)) {
        if (ncode < 0x80) return 0;
        uint32_t stage = (nvn_capture_u32((const uint8_t *)code + 0x30) >> 10) & 15;
        return stage >= 1 && stage <= 5;
    }
    const uint8_t *c = control;
    return nvn_capture_u32(c + 0x748) && nvn_capture_u32(c + 0x74c) &&
           nvn_capture_u32(c + 0x750) && (magic != UINT32_C(0x12345679) || ncode >= 0x30);
}
static int nvn_capture_write_all(int fd, const void *data, size_t n) {
    const uint8_t *p = data;
    while (n) {
        ssize_t done = write(fd, p, n);
        if (done < 0 && errno == EINTR) continue;
        if (done <= 0) return 0;
        p += done; n -= (size_t)done;
    }
    return 1;
}
static void nvn_capture_failure(nvn_capture_state *s, const char *what) {
    s->totals.failures++;
    NVN_CAPTURE_LOG("[nvn capture] FAILED: %s (errno=%d)\n", what, errno);
}
static int nvn_capture_row(nvn_capture_state *s, const char *event) {
    if (!s->registration) return 1;
    if (s->broken) return 0;
    char row[2048];
    nvn_capture_totals *t = &s->totals;
    int n = snprintf(row, sizeof row,
        "{\"schema\":1,\"seq\":%" PRIu64 ",%s,\"totals\":{"
        "\"programs\":%" PRIu64 ",\"expected_stages\":%" PRIu64 ",\"register_stages\":%" PRIu64
        ",\"mapped_stages\":%" PRIu64 ",\"deferred_stages\":%" PRIu64 ",\"invalid_stages\":%" PRIu64
        ",\"draw_stages\":%" PRIu64 ",\"captured_unique\":%" PRIu64 ",\"duplicates\":%" PRIu64
        ",\"unresolved_deferred\":%" PRIu64 ",\"failures\":%" PRIu64 ",\"bytes_written\":%" PRIu64 "}}\n",
        s->sequence, event, t->programs, t->expected_stages, t->register_stages, t->mapped_stages,
        t->deferred_stages, t->invalid_stages, t->draw_stages, t->captured_unique, t->duplicates,
        t->unresolved_deferred, t->failures, t->bytes_written);
    if (n < 0 || (size_t)n >= sizeof row || s->sequence >= NVN_CAPTURE_MAX_EVENTS ||
        (uint64_t)n > NVN_CAPTURE_MAX_LEDGER - s->ledger_bytes ||
        !nvn_capture_write_all(s->ledger, row, (size_t)n)) {
        s->broken = 1; nvn_capture_failure(s, "census ledger write/limit"); return 0;
    }
    s->sequence++; s->ledger_bytes += (uint64_t)n;
    return 1;
}
// Initialization runs under this state's mutex. O_EXCL prevents mixing producer
// runs or overwriting outputs from another process; producer uses a fresh dir.
static void nvn_capture_init(nvn_capture_state *s, const char *directory, int registration) {
    if (s->initialized) return;
    s->initialized = 1; s->registration = registration;
    if (!directory || !*directory) {
        if (registration) nvn_capture_failure(s, "REGISTER requires DM_NVN_SHDUMP directory");
        return;
    }
    s->directory = open(directory, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (s->directory < 0) { nvn_capture_failure(s, "capture directory open"); return; }
    s->keys = calloc(NVN_CAPTURE_SLOTS, sizeof *s->keys);
    s->pending = registration ? calloc(NVN_CAPTURE_SLOTS, sizeof *s->pending) : NULL;
    if (!s->keys || (registration && !s->pending)) { nvn_capture_failure(s, "capture table allocation"); return; }
    if (registration) {
        s->ledger = openat(s->directory, NVN_CAPTURE_LEDGER, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
        if (s->ledger < 0) { nvn_capture_failure(s, "new census ledger open"); return; }
    }
    s->active = 1;
    char event[512];
    snprintf(event, sizeof event, "\"event\":\"begin\",\"mode\":\"register-all\",\"pid\":%ld,"
        "\"limits\":{\"unique\":%u,\"events\":%u,\"bytes\":%" PRIu64 ",\"ledger_bytes\":%" PRIu64 "}",
        (long)getpid(), NVN_CAPTURE_MAX_UNIQUE, NVN_CAPTURE_MAX_EVENTS, NVN_CAPTURE_MAX_BYTES, NVN_CAPTURE_MAX_LEDGER);
    nvn_capture_row(s, event);
}
static nvn_capture_pending *nvn_capture_stage_slot(nvn_capture_state *s, uint64_t serial, unsigned index, int make) {
    uint64_t start = (serial * UINT64_C(11400714819323198485) + index) & (NVN_CAPTURE_SLOTS - 1);
    for (unsigned n = 0; n < NVN_CAPTURE_SLOTS; n++) {
        nvn_capture_pending *p = &s->pending[(start + n) & (NVN_CAPTURE_SLOTS - 1)];
        if (p->used && p->serial == serial && p->index == index) return p;
        if (!p->used) {
            if (!make) return NULL;
            *p = (nvn_capture_pending){ .serial = serial, .index = index, .used = 1 }; return p;
        }
    }
    return NULL;
}
static void nvn_capture_program(nvn_capture_state *s, uint64_t serial, const void *program, unsigned stages) {
    pthread_mutex_lock(&s->mutex);
    if (s->active && s->registration && !s->broken) {
        s->totals.programs++; s->totals.expected_stages += stages;
        char event[256]; snprintf(event, sizeof event,
            "\"event\":\"program\",\"serial\":%" PRIu64 ",\"program\":\"%" PRIxPTR "\",\"stages\":%u",
            serial, (uintptr_t)program, stages);
        nvn_capture_row(s, event);
    }
    pthread_mutex_unlock(&s->mutex);
}
static int nvn_capture_new_file(nvn_capture_state *s, const char *name, const void *data, size_t length) {
    int fd = openat(s->directory, name, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) return 0;
    int ok = nvn_capture_write_all(fd, data, length);
    if (close(fd)) ok = 0;
    if (!ok) unlinkat(s->directory, name, 0); // Only the file created by this call.
    return ok;
}
// Caller supplies the exact cached intrinsic key and code mapping proof. Source
// pointers are used only synchronously while the game guarantees their lifetime.
static void nvn_capture_stage(nvn_capture_state *s, uint64_t serial, unsigned index, int draw,
                              const void *control, const void *code, int mapped, const uint8_t key[8]) {
    pthread_mutex_lock(&s->mutex);
    if (!s->active || s->broken) { pthread_mutex_unlock(&s->mutex); return; }
    const char *status = "error";
    uint32_t nctl = 0, ncode = 0; uint8_t digest[32] = {0}; char hex[65] = {0};
    nvn_capture_pending *pending = NULL;
    if (s->registration) {
        if (draw) s->totals.draw_stages++; else s->totals.register_stages++;
        pending = nvn_capture_stage_slot(s, serial, index, !draw);
        if (!pending) { nvn_capture_failure(s, "stage census table/missing registration"); goto row; }
    }
    if (!nvn_capture_lengths(control, &nctl, &ncode)) {
        status = "invalid"; s->totals.invalid_stages++; nvn_capture_failure(s, "invalid control/code lengths"); goto row;
    }
    if (!mapped) {
        status = "deferred";
        if (!draw) { s->totals.deferred_stages++; if (pending) { pending->deferred = 1; s->totals.unresolved_deferred++; } }
        goto row;
    }
    if (!draw) s->totals.mapped_stages++;
    if (!key || !nvn_capture_code_valid(control, code, ncode)) {
        status = "invalid"; s->totals.invalid_stages++; nvn_capture_failure(s, "invalid mapped shader/header"); goto row;
    }
    CC_SHA256_CTX hash; CC_SHA256_Init(&hash);
    CC_SHA256_Update(&hash, control, nctl); CC_SHA256_Update(&hash, code, ncode); CC_SHA256_Final(digest, &hash);
    for (unsigned i = 0; i < sizeof digest; i++) snprintf(hex + 2 * i, 3, "%02x", digest[i]);
    if (memcmp(key, digest, 8)) { nvn_capture_failure(s, "intrinsic key changed before capture"); goto row; }
    uint64_t start; memcpy(&start, digest, 8); start &= NVN_CAPTURE_SLOTS - 1;
    nvn_capture_key *slot = NULL;
    for (unsigned n = 0; n < NVN_CAPTURE_SLOTS; n++) {
        nvn_capture_key *candidate = &s->keys[(start + n) & (NVN_CAPTURE_SLOTS - 1)];
        if (!candidate->used || !memcmp(candidate->digest, digest, 8)) { slot = candidate; break; }
    }
    if (!slot) { nvn_capture_failure(s, "key table full"); goto row; }
    if (slot->used) {
        if (memcmp(slot->digest, digest, 32) || slot->control_bytes != nctl || slot->code_bytes != ncode) {
            nvn_capture_failure(s, "intrinsic short-key collision"); goto row;
        }
        status = "duplicate"; s->totals.duplicates++;
    } else {
        uint64_t bytes = (uint64_t)nctl + ncode;
        if (s->totals.captured_unique >= NVN_CAPTURE_MAX_UNIQUE || bytes > NVN_CAPTURE_MAX_BYTES - s->totals.bytes_written) {
            nvn_capture_failure(s, "shader capture byte/count limit"); goto row;
        }
        char ctl_name[32], code_name[32];
        snprintf(ctl_name, sizeof ctl_name, "%.16s.ctl", hex); snprintf(code_name, sizeof code_name, "%.16s.code", hex);
        if (!nvn_capture_new_file(s, ctl_name, control, nctl)) { nvn_capture_failure(s, "new control file write"); goto row; }
        if (!nvn_capture_new_file(s, code_name, code, ncode)) {
            unlinkat(s->directory, ctl_name, 0); nvn_capture_failure(s, "new code file write"); goto row;
        }
        memcpy(slot->digest, digest, 32); slot->control_bytes = nctl; slot->code_bytes = ncode; slot->used = 1;
        s->totals.captured_unique++; s->totals.bytes_written += bytes; status = "captured";
    }
    if (pending && pending->deferred) { pending->deferred = 0; s->totals.unresolved_deferred--; }
row:;
    char event[768]; snprintf(event, sizeof event,
        "\"event\":\"stage\",\"origin\":\"%s\",\"serial\":%" PRIu64 ",\"index\":%u,\"status\":\"%s\","
        "\"control_address\":\"%" PRIxPTR "\",\"code_address\":\"%" PRIxPTR "\",\"control_bytes\":%u,"
        "\"code_bytes\":%u,\"key\":\"%.16s\",\"sha256\":\"%s\"",
        draw ? "draw" : "register", serial, index, status, (uintptr_t)control, (uintptr_t)code, nctl, ncode, hex, hex);
    nvn_capture_row(s, event);
    pthread_mutex_unlock(&s->mutex);
}
