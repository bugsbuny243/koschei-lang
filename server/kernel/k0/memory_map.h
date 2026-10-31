#ifndef KOSCHEI_K0_MEMORY_MAP_H
#define KOSCHEI_K0_MEMORY_MAP_H
/* Freestanding UEFI memory-map validation. No allocation or map-range access. */
typedef unsigned char K_U8;
typedef unsigned int K_U32;
typedef unsigned long long K_U64;

typedef struct {
    K_U32 type;
    K_U32 pad;
    K_U64 physical_start;
    K_U64 virtual_start;
    K_U64 number_of_pages;
    K_U64 attributes;
} K0_MEMORY_DESCRIPTOR;

typedef struct {
    K_U64 descriptors;
    K_U64 conventional_pages;
    K_U64 candidate_start;
    K_U64 candidate_pages;
} K0_MEMORY_PLAN;

#define K0_PAGE_SIZE 4096ULL
#define K0_MEMORY_MAP_LIMIT 65536ULL
#define K0_PLAN_PAGES 16ULL
#define K0_CONVENTIONAL_MEMORY 7U

_Static_assert(sizeof(K0_MEMORY_DESCRIPTOR) == 40, "UEFI descriptor layout");

/* Unaligned-safe descriptor reads; stride may exceed sizeof descriptor. */
static K0_MEMORY_DESCRIPTOR k0_read_descriptor(const K_U8 *ptr) {
    K0_MEMORY_DESCRIPTOR d;
    K_U8 *dst = (K_U8 *)&d;
    for (K_U64 i = 0; i < sizeof(d); i++) dst[i] = ptr[i];
    return d;
}

/* UNKNOWN memory types always unavailable; validate ALL regions first. */
static int k0_memory_validate_plan(const void *map, K_U64 bytes, K_U64 stride,
                                   K_U32 version, K0_MEMORY_PLAN *plan) {
    if (!map || !plan || version != 1 || stride < sizeof(K0_MEMORY_DESCRIPTOR) ||
        (stride & 7U) != 0 || !bytes || bytes > K0_MEMORY_MAP_LIMIT ||
        bytes % stride != 0) return 0;
    const K_U8 *base = (const K_U8 *)map;
    K_U64 count = bytes / stride;
    K_U64 total = 0;
    K_U64 chosen = 0;
    int found = 0;
    for (K_U64 i = 0; i < count; i++) {
        K0_MEMORY_DESCRIPTOR a = k0_read_descriptor(base + i * stride);
        if (!a.number_of_pages || (a.physical_start & (K0_PAGE_SIZE - 1)) ||
            a.number_of_pages > (~(K_U64)0 / K0_PAGE_SIZE) ||
            a.physical_start > (~(K_U64)0 - a.number_of_pages * K0_PAGE_SIZE))
            return 0;
        K_U64 a_end = a.physical_start + a.number_of_pages * K0_PAGE_SIZE;
        for (K_U64 j = 0; j < i; j++) {
            K0_MEMORY_DESCRIPTOR b = k0_read_descriptor(base + j * stride);
            K_U64 b_end = b.physical_start + b.number_of_pages * K0_PAGE_SIZE;
            if (a.physical_start < b_end && b.physical_start < a_end) return 0;
        }
        if (a.type == K0_CONVENTIONAL_MEMORY) {
            if (total > ~(K_U64)0 - a.number_of_pages) return 0;
            total += a.number_of_pages;
            K_U64 candidate = a.physical_start < 0x100000ULL ? 0x100000ULL : a.physical_start;
            if (candidate <= a_end && a_end - candidate >= K0_PLAN_PAGES * K0_PAGE_SIZE &&
                (!found || candidate < chosen)) {
                chosen = candidate;
                found = 1;
            }
        }
    }
    if (!found) return 0;
    /* Only commit after validation. NEVER claim ownership of UEFI pages. */
    K0_MEMORY_PLAN next = {count, total, chosen, K0_PLAN_PAGES};
    *plan = next;
    return 1;
}
#endif
