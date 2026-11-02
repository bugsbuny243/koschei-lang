#ifndef KOSCHEI_K0_CR3_FIRMWARE_MAP_PROVENANCE_H
#define KOSCHEI_K0_CR3_FIRMWARE_MAP_PROVENANCE_H
/*
 * Fail-closed SOFTWARE correlation of an owned-CR3 candidate with the exact
 * captured UEFI memory map. No firmware calls, CR3 writes or hardware traps.
 *
 * A descriptor type is only provenance for the *physical reservation*, not
 * proof that arbitrary caller-supplied addresses really contain live code,
 * stack, IDT or GDT. Loaded-image/stack register evidence is still missing.
 */
#include "cr3_transition_preflight.h"

#define K0_EFI_LOADER_CODE 1U
#define K0_EFI_LOADER_DATA 2U
#define K0_EFI_BOOT_SERVICES_CODE 3U
#define K0_EFI_BOOT_SERVICES_DATA 4U
#define K0_EFI_MEMORY_RUNTIME (1ULL << 63)

/* The whole span must fit exactly inside a single map descriptor; do not
 * "stitch" arbitrary adjacent descriptors of mixed provenance together.
 * Validation of descriptors, lengths and overlaps is performed first.
 */
static int k0_cr3_efi_span_type(const void *map, K_U64 size,
                                K_U64 stride, K_U64 begin, K_U64 end,
                                K_U32 type_a, K_U32 type_b) {
    const K_U8 *raw = (const K_U8 *)map;
    if (!raw || !stride || begin >= end) return 0;
    for (K_U64 off = 0; off < size; off += stride) {
        K0_MEMORY_DESCRIPTOR d = k0_read_descriptor(raw + off);
        K_U64 d_end = d.physical_start + d.number_of_pages * K0_PAGE_SIZE;
        if (begin >= d.physical_start && end <= d_end &&
            (d.type == type_a || d.type == type_b) &&
            !(d.attributes & K0_EFI_MEMORY_RUNTIME))
            return 1;
    }
    return 0;
}

static int k0_cr3_uefi_map_provenance_preflight(
    const K0_CR3_PROPOSAL *proposal, const K0_PAGE_POOL *pool,
    const void *uefi_map, K_U64 map_bytes, K_U64 descriptor_stride,
    K_U32 descriptor_version, int exit_boot_services_succeeded) {
    K0_MEMORY_PLAN current_plan = {0};
    if (exit_boot_services_succeeded != 1 ||
        !k0_cr3_transition_preflight(proposal, pool) ||
        !k0_memory_validate_plan(uefi_map, map_bytes, descriptor_stride,
                                 descriptor_version, &current_plan) ||
        current_plan.candidate_start != pool->base ||
        current_plan.candidate_pages != K0_PLAN_PAGES)
        return 0;

    /* Bind the entire allocator candidate, not just the claimed entries, to
     * one conventional descriptor. Firmware runtime and device pages never
     * inherit post-ExitBootServices ownership.
     */
    const K_U64 pool_end = pool->base + K0_PLAN_PAGES * K0_PAGE_SIZE;
    if (!k0_cr3_efi_span_type(uefi_map, map_bytes, descriptor_stride,
                              pool->base, pool_end,
                              K0_CONVENTIONAL_MEMORY, K0_CONVENTIONAL_MEMORY))
        return 0;

    for (K_U32 i = 0; i < proposal->reservation_count; ++i) {
        const K0_CR3_RESERVATION *r = &proposal->reservations[i];
        K_U64 end = 0;
        K_U32 first_type, second_type;
        if (!k0_cr3_bounds(r->pa, r->pages, &end)) return 0;
        if (r->provenance == K0_CR3_PROV_IMAGE) {
            first_type = K0_EFI_LOADER_CODE;
            second_type = K0_EFI_BOOT_SERVICES_CODE;
        } else if (r->provenance == K0_CR3_PROV_STACK ||
                   r->provenance == K0_CR3_PROV_CONTROL) {
            first_type = K0_EFI_LOADER_DATA;
            second_type = K0_EFI_BOOT_SERVICES_DATA;
        } else {
            return 0;
        }
        if (!k0_cr3_efi_span_type(uefi_map, map_bytes, descriptor_stride,
                                  r->pa, end, first_type, second_type))
            return 0;
    }

    for (K_U32 i = 0; i < 4; ++i) {
        K_U64 frame = proposal->root_frames[i];
        if (!k0_cr3_efi_span_type(uefi_map, map_bytes, descriptor_stride,
                                  frame, frame + K0_PAGE_SIZE,
                                  K0_CONVENTIONAL_MEMORY,
                                  K0_CONVENTIONAL_MEMORY))
            return 0;
    }
    return 1;
}
#endif
