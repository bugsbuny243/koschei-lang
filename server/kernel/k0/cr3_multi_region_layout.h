#ifndef KOSCHEI_K0_MULTI_REGION_TRANSITION_LAYOUT_H
#define KOSCHEI_K0_MULTI_REGION_TRANSITION_LAYOUT_H
/*
 * HOST-ONLY preflight: materialize a logically complete candidate x86-64
 * PML4/PDPT/PD/PT hierarchy for a *synthetic* identity-mapped transition
 * manifest, using only claimed frame identifiers. NEVER writes physical
 * frames, CR3, EFER, GDT or IDT. Not an executable kernel address space.
 *
 * Deliberately supports ONE PML4 + ONE PDPT + ONE PD, with multiple PTs
 * in distinct 2 MiB windows inside the SAME 1 GiB VA range. All 4KiB
 * leaves must be explicitly declared. Any larger topology fails closed.
 */
#include "cr3_firmware_map_provenance.h"
#include "live_cr3_inspection.h"

#define K0_MR_MAX_FRAMES 16U
#define K0_MR_MAX_PT 13U
#define K0_MR_P 1ULL
#define K0_MR_RW 2ULL
#define K0_MR_NX (1ULL << 63)

typedef struct {
    K_U64 physical_frame;
    K_U64 entries[512];
} K0_MR_TABLE;

typedef struct {
    K0_MR_TABLE tables[K0_MR_MAX_FRAMES];
    K_U32 frame_count;
    K_U32 pt_count;
    K_U32 mapped_pages;
    K_U32 ready;
    K_U64 root;
    K_U64 pool_epoch;
} K0_MR_LAYOUT;

static int k0_mr_read(void *opaque, K_U64 page, K_U32 slot, K_U64 *out) {
    const K0_MR_LAYOUT *m = (const K0_MR_LAYOUT *)opaque;
    if (!m || !m->ready || !out || slot >= 512U) return 0;
    for (K_U32 i = 0; i < m->frame_count; ++i) {
        if (m->tables[i].physical_frame == page) {
            *out = m->tables[i].entries[slot];
            return 1;
        }
    }
    return 0;
}

static int k0_mr_build(const K0_CR3_PROPOSAL *p, const K0_PAGE_POOL *pool,
                       const void *map, K_U64 map_bytes, K_U64 stride,
                       K_U32 version, int exited,
                       const K_U64 *frames, K_U32 frame_count,
                       K0_MR_LAYOUT *out) {
    if (out) out->ready = 0;
    if (!out || !p || !pool || !frames ||
        frame_count < 4 || frame_count > K0_MR_MAX_FRAMES ||
        !k0_cr3_uefi_map_provenance_preflight(
            p, pool, map, map_bytes, stride, version, exited))
        return 0;
    /* Exactly the same 4 primary frames used by the manifest: PML4,
     * PDPT, PD and the first PT. All supplementary PT pages must also
     * be claimed and identity-reachable in the proposed address space.
     */
    for (K_U32 i = 0; i < frame_count; ++i) {
        if (!frames[i] || frames[i] == p->live.old_cr3 ||
            !k0_pool_is_claimed(pool, frames[i]) ||
            !k0_cr3_find(p, frames[i], K0_CR3_WRITE,
                        K0_CR3_PROV_POOL))
            return 0;
        if (i < 4 && frames[i] != p->root_frames[i]) return 0;
        for (K_U32 j = 0; j < i; ++j)
            if (frames[i] == frames[j]) return 0;
    }

    K_U32 pd_indices[K0_MR_MAX_PT] = {0};
    K_U32 pt_count = 0, mapped_pages = 0;
    K_U32 pml4 = (K_U32)((p->mappings[0].va >> 39) & 511ULL);
    K_U32 pdpt = (K_U32)((p->mappings[0].va >> 30) & 511ULL);
    for (K_U32 i = 0; i < p->mapping_count; ++i) {
        const K0_CR3_MAPPING *m = &p->mappings[i];
        if (mapped_pages > 4096U - m->pages) return 0;
        mapped_pages += (K_U32)m->pages;
        for (K_U64 n = 0; n < m->pages; ++n) {
            K_U64 va = m->va + n * K0_PAGE_SIZE;
            if (((va >> 39) & 511ULL) != pml4 ||
                ((va >> 30) & 511ULL) != pdpt ||
                va < 0x100000ULL ||
                va >= 0xffffffffffff0000ULL)
                return 0;
            K_U32 pd = (K_U32)((va >> 21) & 511ULL);
            K_U32 j = 0;
            for (; j < pt_count; ++j)
                if (pd_indices[j] == pd) break;
            if (j == pt_count) {
                if (pt_count == K0_MR_MAX_PT) return 0;
                pd_indices[pt_count++] = pd;
            }
        }
    }
    if (!pt_count || frame_count != 3U + pt_count) return 0;

    for (K_U32 i = 0; i < frame_count; ++i) {
        out->tables[i].physical_frame = frames[i];
        for (K_U32 s = 0; s < 512; ++s)
            out->tables[i].entries[s] = 0;
    }
    out->tables[0].entries[pml4] = frames[1] | K0_MR_P | K0_MR_RW;
    out->tables[1].entries[pdpt] = frames[2] | K0_MR_P | K0_MR_RW;
    for (K_U32 i = 0; i < pt_count; ++i)
        out->tables[2].entries[pd_indices[i]] =
            frames[3 + i] | K0_MR_P | K0_MR_RW;

    for (K_U32 i = 0; i < p->mapping_count; ++i) {
        const K0_CR3_MAPPING *m = &p->mappings[i];
        for (K_U64 n = 0; n < m->pages; ++n) {
            K_U64 va = m->va + n * K0_PAGE_SIZE;
            K_U64 pa = m->pa + n * K0_PAGE_SIZE;
            K_U32 pd = (K_U32)((va >> 21) & 511ULL), j = 0;
            for (; j < pt_count; ++j)
                if (pd_indices[j] == pd) break;
            if (j == pt_count) { out->ready = 0; return 0; }
            K_U32 pt_slot = (K_U32)((va >> 12) & 511ULL);
            if (out->tables[3 + j].entries[pt_slot]) {
                out->ready = 0;
                return 0;
            }
            out->tables[3 + j].entries[pt_slot] =
                pa | K0_MR_P |
                ((m->flags & K0_CR3_WRITE) ? K0_MR_RW : 0ULL) |
                ((m->flags & K0_CR3_EXEC) ? 0ULL : K0_MR_NX);
        }
    }
    out->root = frames[0];
    out->frame_count = frame_count;
    out->pt_count = pt_count;
    out->mapped_pages = mapped_pages;
    out->pool_epoch = pool->epoch;
    out->ready = 1;

    /* Validate the resulting BYTES through a separate PTE decoder,
     * including the entire map and the non-present sentinel addresses.
     */
    for (K_U32 i = 0; i < p->mapping_count; ++i) {
        const K0_CR3_MAPPING *m = &p->mappings[i];
        for (K_U64 n = 0; n < m->pages; ++n) {
            K_U64 va = m->va + n * K0_PAGE_SIZE;
            K0_CR3_I_RESULT result = {0};
            if (!k0_cr3_inspect_translation(
                     out->root, va, k0_mr_read, out, &result) ||
                result.physical_address != m->pa + n * K0_PAGE_SIZE ||
                result.leaf_page_shift != 12 ||
                result.effective_user ||
                result.effective_write !=
                  ((m->flags & K0_CR3_WRITE) != 0) ||
                result.effective_nx !=
                  ((m->flags & K0_CR3_EXEC) == 0)) {
                out->ready = 0;
                return 0;
            }
        }
    }
    K0_CR3_I_RESULT denied = {0};
    if (k0_cr3_inspect_translation(out->root, 0x1000ULL,
                                  k0_mr_read, out, &denied) ||
        k0_cr3_inspect_translation(out->root, 0xfffffffffffff000ULL,
                                  k0_mr_read, out, &denied)) {
        out->ready = 0;
        return 0;
    }
    return 1;
}
#endif
