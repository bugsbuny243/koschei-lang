#ifndef KOSCHEI_K0_CR3_TRANSITION_PREFLIGHT_H
#define KOSCHEI_K0_CR3_TRANSITION_PREFLIGHT_H
/*
 * Software-only, fail-closed preflight of a PROPOSED replacement-CR3
 * address-space manifest. Does NOT construct page tables or write CR3.
 * All physical provenance and live register snapshots must be independently
 * captured and authenticated before any future hardware activation.
 */
#include "page_pool.h"
#include <stdint.h>

#define K0_CR3_MAX_MAPPINGS 32U
#define K0_CR3_MAX_RESERVATIONS 16U
#define K0_CR3_MAX_COVER_PAGES 4096ULL
#define K0_CR3_PHYS_MASK 0x000ffffffffff000ULL
#define K0_CR3_WRITE 1U
#define K0_CR3_EXEC 2U
#define K0_CR3_USER 4U
#define K0_CR3_PROV_POOL 1U
#define K0_CR3_PROV_IMAGE 2U
#define K0_CR3_PROV_STACK 3U
#define K0_CR3_PROV_CONTROL 4U

typedef struct {
    K_U64 va;
    K_U64 pa;
    K_U64 pages;
    K_U32 flags;       /* WRITE/EXEC; USER forbidden; W+X forbidden */
    K_U32 provenance;  /* explicitly reserved or claimed pool */
} K0_CR3_MAPPING;

typedef struct {
    K_U64 pa;
    K_U64 pages;
    K_U32 provenance;  /* IMAGE, STACK, CONTROL; never POOL */
} K0_CR3_RESERVATION;

typedef struct {
    K_U64 old_cr3;
    K_U64 cr0;
    K_U64 cr4;
    K_U64 efer;
    K_U64 rflags;
    uint16_t cs;
    uint16_t nx_cpuid_supported;
    K_U64 rip;
    K_U64 rsp;
    K_U64 pf_entry;
    K_U64 gp_entry;
    K_U64 df_entry;
    K_U64 transition_entry;
    K_U64 code_start, code_end;      /* exclusive and page-aligned */
    K_U64 stack_start, stack_end;
    K_U64 idt_start, idt_end;
    K_U64 gdt_start, gdt_end;
} K0_CR3_LIVE_CONTEXT;

typedef struct {
    K0_CR3_MAPPING mappings[K0_CR3_MAX_MAPPINGS];
    K0_CR3_RESERVATION reservations[K0_CR3_MAX_RESERVATIONS];
    K_U32 mapping_count, reservation_count;
    K_U64 root_frames[4];            /* claimed, distinct page-table frames */
    K_U64 pool_epoch;                /* freezes preflight ownership snapshot */
    K0_CR3_LIVE_CONTEXT live;
} K0_CR3_PROPOSAL;

static int k0_cr3_canonical(K_U64 v) {
    return (v & (1ULL << 47)) ? (v >> 48) == 0xffffULL : (v >> 48) == 0;
}

static int k0_cr3_bounds(K_U64 start, K_U64 pages, K_U64 *end) {
    if (!start || (start & (K0_PAGE_SIZE - 1)) ||
        !pages || pages > K0_CR3_MAX_COVER_PAGES ||
        pages > (~(K_U64)0 - start) / K0_PAGE_SIZE)
        return 0;
    *end = start + pages * K0_PAGE_SIZE;
    return *end > start;
}

static int k0_cr3_overlap(K_U64 a, K_U64 a_end, K_U64 b, K_U64 b_end) {
    return a < b_end && b < a_end;
}

/* Every non-pool physical mapping must be covered by exactly one previously
 * reserved range. The reservation list is a CLAIM, not UEFI map verification.
 */
static int k0_cr3_reserved_span(const K0_CR3_PROPOSAL *p,
                                const K0_CR3_MAPPING *m, K_U64 m_end) {
    for (K_U32 i = 0; i < p->reservation_count; ++i) {
        const K0_CR3_RESERVATION *r = &p->reservations[i];
        K_U64 end = 0;
        if (r->provenance != m->provenance ||
            !k0_cr3_bounds(r->pa, r->pages, &end)) continue;
        if (m->pa >= r->pa && m_end <= end) return 1;
    }
    return 0;
}

static int k0_cr3_mapping_valid(const K0_CR3_PROPOSAL *p,
                                 const K0_PAGE_POOL *pool,
                                 const K0_CR3_MAPPING *m) {
    K_U64 va_end = 0, pa_end = 0;
    if (!k0_cr3_bounds(m->va, m->pages, &va_end) ||
        !k0_cr3_bounds(m->pa, m->pages, &pa_end) ||
        !k0_cr3_canonical(m->va) || !k0_cr3_canonical(va_end - 1) ||
        ((m->pa | (pa_end - K0_PAGE_SIZE)) & ~K0_CR3_PHYS_MASK) ||
        (m->flags & ~(K0_CR3_WRITE | K0_CR3_EXEC)) ||
        ((m->flags & (K0_CR3_WRITE | K0_CR3_EXEC)) ==
                       (K0_CR3_WRITE | K0_CR3_EXEC)) ||
        m->provenance < K0_CR3_PROV_POOL ||
        m->provenance > K0_CR3_PROV_CONTROL)
        return 0;
    if (m->provenance == K0_CR3_PROV_POOL) {
        for (K_U64 i = 0; i < m->pages; ++i)
            if (!k0_pool_is_claimed(pool, m->pa + i * K0_PAGE_SIZE))
                return 0;
        return m->va == m->pa;
    }
    /* The transition assumption is firmware identity-mapped critical code,
     * stack and descriptors. No implicit VA->PA translation is inferred.
     */
    return m->va == m->pa && k0_cr3_reserved_span(p, m, pa_end);
}

static const K0_CR3_MAPPING *k0_cr3_find(
    const K0_CR3_PROPOSAL *p, K_U64 address, K_U32 desired_flags,
    K_U32 desired_provenance) {
    if (!k0_cr3_canonical(address)) return 0;
    for (K_U32 i = 0; i < p->mapping_count; ++i) {
        const K0_CR3_MAPPING *m = &p->mappings[i];
        K_U64 end = m->va + m->pages * K0_PAGE_SIZE;
        if (m->va <= address && address < end &&
            m->flags == desired_flags && m->provenance == desired_provenance)
            return m;
    }
    return 0;
}

static int k0_cr3_covers_range(
    const K0_CR3_PROPOSAL *p, K_U64 start, K_U64 end,
    K_U32 flags, K_U32 provenance) {
    if (!start || start >= end || (start & (K0_PAGE_SIZE - 1)) ||
        (end & (K0_PAGE_SIZE - 1)) ||
        (end - start) / K0_PAGE_SIZE > K0_CR3_MAX_COVER_PAGES ||
        !k0_cr3_canonical(start) || !k0_cr3_canonical(end - 1))
        return 0;
    for (K_U64 page = start; page < end; page += K0_PAGE_SIZE)
        if (!k0_cr3_find(p, page, flags, provenance)) return 0;
    return 1;
}

/* No mutation; a success means only that a SYNTHETIC manifest appears to
 * cover explicitly declared critical ranges. It is NOT CPU page-table proof.
 */
static int k0_cr3_transition_preflight(const K0_CR3_PROPOSAL *p,
                                       const K0_PAGE_POOL *pool) {
    if (!p || !pool || !pool->initialized || !pool->epoch ||
        !p->pool_epoch || p->pool_epoch != pool->epoch ||
        !p->mapping_count || p->mapping_count > K0_CR3_MAX_MAPPINGS ||
        !p->reservation_count ||
        p->reservation_count > K0_CR3_MAX_RESERVATIONS)
        return 0;
    const K0_CR3_LIVE_CONTEXT *x = &p->live;
    /* CR0.PE/PG/WP, CR4.PAE but NO LA57/PCIDE, EFER.LME/LMA/NXE,
     * ring 0, RFLAGS bit 1 set and IF clear.
     */
    if (!x->old_cr3 || (x->old_cr3 & (K0_PAGE_SIZE - 1)) ||
        (x->old_cr3 & ~K0_CR3_PHYS_MASK) ||
        (x->cr0 & ((1ULL << 0) | (1ULL << 16) | (1ULL << 31))) !=
                    ((1ULL << 0) | (1ULL << 16) | (1ULL << 31)) ||
        (x->cr4 & (1ULL << 5)) == 0 ||
        (x->cr4 & ((1ULL << 12) | (1ULL << 17))) != 0 ||
        (x->efer & ((1ULL << 8) | (1ULL << 10) | (1ULL << 11))) !=
                     ((1ULL << 8) | (1ULL << 10) | (1ULL << 11)) ||
        (x->rflags & (2ULL | (1ULL << 9))) != 2ULL ||
        !x->cs || (x->cs & 3U) || x->nx_cpuid_supported != 1)
        return 0;
    K_U64 pool_end = pool->base + K0_PLAN_PAGES * K0_PAGE_SIZE;
    for (K_U32 i = 0; i < p->reservation_count; ++i) {
        const K0_CR3_RESERVATION *r = &p->reservations[i];
        K_U64 end = 0;
        if (r->provenance < K0_CR3_PROV_IMAGE ||
            r->provenance > K0_CR3_PROV_CONTROL ||
            !k0_cr3_bounds(r->pa, r->pages, &end) ||
            k0_cr3_overlap(r->pa, end, pool->base, pool_end))
            return 0;
        for (K_U32 j = 0; j < i; ++j) {
            const K0_CR3_RESERVATION *earlier = &p->reservations[j];
            K_U64 old_end = earlier->pa + earlier->pages * K0_PAGE_SIZE;
            if (k0_cr3_overlap(r->pa, end, earlier->pa, old_end))
                return 0;
        }
    }
    for (K_U32 i = 0; i < 4; ++i) {
        if (!k0_pool_is_claimed(pool, p->root_frames[i]) ||
            p->root_frames[i] == x->old_cr3) return 0;
        for (K_U32 j = 0; j < i; ++j)
            if (p->root_frames[i] == p->root_frames[j]) return 0;
        if (!k0_cr3_find(p, p->root_frames[i], K0_CR3_WRITE,
                         K0_CR3_PROV_POOL)) {
            /* Claim addresses may be high-half aliased in future designs,
             * but this preflight deliberately requires a DIRECT identity
             * mapping to keep table writes reachable across transition.
             */
            return 0;
        }
    }
    for (K_U32 i = 0; i < p->mapping_count; ++i) {
        const K0_CR3_MAPPING *m = &p->mappings[i];
        if (!k0_cr3_mapping_valid(p, pool, m)) return 0;
        K_U64 va_end = m->va + m->pages * K0_PAGE_SIZE;
        K_U64 pa_end = m->pa + m->pages * K0_PAGE_SIZE;
        for (K_U32 j = 0; j < i; ++j) {
            const K0_CR3_MAPPING *prior = &p->mappings[j];
            K_U64 old_va_end = prior->va + prior->pages * K0_PAGE_SIZE;
            K_U64 old_pa_end = prior->pa + prior->pages * K0_PAGE_SIZE;
            if (k0_cr3_overlap(m->va, va_end, prior->va, old_va_end) ||
                k0_cr3_overlap(m->pa, pa_end, prior->pa, old_pa_end))
                return 0;
        }
    }
    if (!k0_cr3_covers_range(p, x->code_start, x->code_end,
                            K0_CR3_EXEC, K0_CR3_PROV_IMAGE) ||
        !k0_cr3_covers_range(p, x->stack_start, x->stack_end,
                            K0_CR3_WRITE, K0_CR3_PROV_STACK) ||
        !k0_cr3_covers_range(p, x->idt_start, x->idt_end,
                            0, K0_CR3_PROV_CONTROL) ||
        !k0_cr3_covers_range(p, x->gdt_start, x->gdt_end,
                            0, K0_CR3_PROV_CONTROL))
        return 0;
    const K_U64 handlers[] = {
        x->rip, x->pf_entry, x->gp_entry,
        x->df_entry, x->transition_entry
    };
    for (K_U32 i = 0; i < sizeof(handlers)/sizeof(handlers[0]); ++i) {
        if (handlers[i] < x->code_start || handlers[i] >= x->code_end ||
            !k0_cr3_find(p, handlers[i], K0_CR3_EXEC,
                         K0_CR3_PROV_IMAGE)) return 0;
    }
    return x->rsp > x->stack_start && x->rsp <= x->stack_end &&
           k0_cr3_find(p, x->rsp - 1, K0_CR3_WRITE,
                       K0_CR3_PROV_STACK) != 0;
}
#endif
