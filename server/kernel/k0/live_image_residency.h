#ifndef KOSCHEI_K0_LIVE_IMAGE_RESIDENCY_H
#define KOSCHEI_K0_LIVE_IMAGE_RESIDENCY_H
/*
 * Software-only correlation of an EFI LoadedImage-protocol observation with
 * the validated *final* firmware memory-map snapshot and current RIP/RSP.
 *
 * This does not walk the live CR3 page tables. Equating a UEFI descriptor's
 * physical range with a currently mapped virtual address still relies on
 * the diagnostic OVMF identity-mapping assumption. No owned CR3 is installed.
 */
#include "memory_map.h"

#define K0_LIVE_IMAGE_MAX_SIZE (32ULL * 1024ULL * 1024ULL)
#define K0_EFI_LOADER_CODE_TYPE 1U
#define K0_EFI_LOADER_DATA_TYPE 2U
#define K0_EFI_BOOT_CODE_TYPE 3U
#define K0_EFI_BOOT_DATA_TYPE 4U
#define K0_EFI_RUNTIME_ATTRIBUTE (1ULL << 63)

static int k0_live_img_canonical48(K_U64 a) {
    return (a >> 48) == ((a & (1ULL << 47)) ? 0xffffULL : 0ULL);
}

static int k0_live_img_in_descriptor(
    const void *map, K_U64 map_size, K_U64 stride, K_U64 address,
    K_U32 a, K_U32 b, K_U32 c) {
    const K_U8 *bytes = (const K_U8 *)map;
    for (K_U64 offset = 0; offset < map_size; offset += stride) {
        K0_MEMORY_DESCRIPTOR desc = k0_read_descriptor(bytes + offset);
        const K_U64 last = desc.physical_start +
                           desc.number_of_pages * K0_PAGE_SIZE;
        if (desc.physical_start <= address && address < last &&
            !(desc.attributes & K0_EFI_RUNTIME_ATTRIBUTE) &&
            (desc.type == a || desc.type == b || desc.type == c))
            return 1;
    }
    return 0;
}

static int k0_live_image_residency_preflight(
    const void *map, K_U64 map_size, K_U64 stride, K_U32 version,
    K_U64 image_base, K_U64 image_size,
    K_U64 captured_rip, K_U64 captured_rsp,
    K_U64 claimed_pool_base) {
    K0_MEMORY_PLAN plan = {0};
    if (!k0_memory_validate_plan(map, map_size, stride, version, &plan) ||
        !image_base || (image_base & (K0_PAGE_SIZE - 1)) ||
        !image_size || image_size > K0_LIVE_IMAGE_MAX_SIZE ||
        image_size > ~(K_U64)0 - image_base ||
        !k0_live_img_canonical48(image_base) ||
        !k0_live_img_canonical48(image_base + image_size - 1) ||
        !k0_live_img_canonical48(captured_rip) ||
        !k0_live_img_canonical48(captured_rsp) ||
        captured_rip < image_base ||
        captured_rip >= image_base + image_size ||
        captured_rsp <= 1 ||
        !claimed_pool_base || (claimed_pool_base & (K0_PAGE_SIZE - 1)) ||
        claimed_pool_base > ~(K_U64)0 - K0_PLAN_PAGES * K0_PAGE_SIZE ||
        plan.candidate_start != claimed_pool_base)
        return 0;
    /* The test-only stack and observed code must not alias the claimed
     * table-frame pool. Using rsp-1 addresses the byte just below the
     * current top of the stack.
     */
    const K_U64 pool_end = claimed_pool_base + K0_PLAN_PAGES * K0_PAGE_SIZE;
    if ((captured_rsp - 1 >= claimed_pool_base &&
         captured_rsp - 1 < pool_end) ||
        (image_base < pool_end && claimed_pool_base < image_base + image_size) ||
        !k0_live_img_in_descriptor(map, map_size, stride,
                                  claimed_pool_base, K0_CONVENTIONAL_MEMORY,
                                  K0_CONVENTIONAL_MEMORY, K0_CONVENTIONAL_MEMORY) ||
        !k0_live_img_in_descriptor(map, map_size, stride,
                                  pool_end - 1, K0_CONVENTIONAL_MEMORY,
                                  K0_CONVENTIONAL_MEMORY, K0_CONVENTIONAL_MEMORY))
        return 0;

    /* Only verify observed code/stack locations, NOT every loaded-image
     * page, all PE sections, GDT/IDT provenance, or physical translation.
     */
    if (!k0_live_img_in_descriptor(map, map_size, stride, captured_rip,
        K0_EFI_LOADER_CODE_TYPE, K0_EFI_BOOT_CODE_TYPE,
        K0_EFI_LOADER_CODE_TYPE))
        return 0;
    if (!k0_live_img_in_descriptor(map, map_size, stride, captured_rsp - 1,
        K0_EFI_LOADER_DATA_TYPE, K0_EFI_BOOT_DATA_TYPE,
        K0_CONVENTIONAL_MEMORY))
        return 0;
    return 1;
}
#endif
