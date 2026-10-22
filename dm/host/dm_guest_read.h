// Admit only opened heap bytes or explicitly mapped alias pages, then let the
// kernel copy so a concurrent guest unmap cannot turn diagnostics into a fault.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdatomic.h>
#include <mach/mach.h>

static inline int dm_copy_guest_regions(uint64_t address, void *out, size_t length,
        uint64_t heap, size_t heap_length, uint64_t alias, size_t alias_length,
        const _Atomic uint64_t *mapped_pages) {
    if (!address || !out || !length) return 0;
    int admitted = heap && address >= heap && length <= heap_length && address - heap <= heap_length - length;
    if (!admitted) {
        if (!alias || !mapped_pages || address < alias || length > alias_length || address - alias > alias_length - length) return 0;
        uint64_t first = (address - alias) >> 12, last = (address - alias + length - 1) >> 12;
        for (uint64_t page = first; page <= last; ++page)
            if (!(atomic_load_explicit(&mapped_pages[page >> 6], memory_order_acquire) & (1ull << (page & 63)))) return 0;
    }
    _Static_assert(sizeof(vm_address_t) == sizeof(uint64_t), "guest copy requires LP64 Mach VM addresses");
    vm_size_t copied = 0;
    return vm_read_overwrite(mach_task_self(), (vm_address_t)address,
        (vm_size_t)length, (vm_address_t)(uintptr_t)out, &copied) == KERN_SUCCESS && copied == length;
}
