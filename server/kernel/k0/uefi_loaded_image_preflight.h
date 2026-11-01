#ifndef KOSCHEI_K0_LOADED_IMAGE_PREFLIGHT_H
#define KOSCHEI_K0_LOADED_IMAGE_PREFLIGHT_H
/*
 * K0.4 UEFI image ownership *metadata* only, never an allocation or CR3 map.
 * The UEFI LoadedImageProtocol is acquired while BootServices is available.
 * Descriptor coverage is rechecked on every GetMemoryMap retry; only
 * LoaderCode/LoaderData are accepted. Unknown types and gaps fail closed.
 * The firmware-provided protocol pointer and memory map remain trust inputs.
 */
#include "paging_pe_section_wx.h"
typedef unsigned short K0_EFI_U16;

typedef struct {
    K_U32 data1;
    K0_EFI_U16 data2;
    K0_EFI_U16 data3;
    K_U8 data4[8];
} K0_EFI_GUID;

typedef struct {
    K_U32 revision;
    K_U32 reserved_align;
    void *parent_handle;
    void *system_table;
    void *device_handle;
    void *file_path;
    void *reserved;
    K_U32 load_options_size;
    K_U32 reserved_align2;
    void *load_options;
    void *image_base;
    K_U64 image_size;
    K_U32 image_code_type;
    K_U32 image_data_type;
    void *unload;
} K0_EFI_LOADED_IMAGE;

_Static_assert(sizeof(K0_EFI_GUID) == 16, "UEFI protocol GUID");
_Static_assert(__builtin_offsetof(K0_EFI_LOADED_IMAGE, image_base) == 64,
               "UEFI LoadedImage ImageBase offset");
_Static_assert(__builtin_offsetof(K0_EFI_LOADED_IMAGE, image_size) == 72,
               "UEFI LoadedImage ImageSize offset");
_Static_assert(sizeof(K0_EFI_LOADED_IMAGE) == 96, "UEFI LoadedImage size");

static const K0_EFI_GUID k0_loaded_image_guid = {
    0x5b1b31a1U, 0x9562U, 0x11d2U,
    {0x8e, 0x3f, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}
};

typedef struct {
    K_U64 base;
    K_U64 size;
    K_U64 entry;
    K_U32 descriptor_count;
} K0_LOADED_IMAGE_BOUNDS;

/* Intended for use ONLY after k0_memory_validate_plan succeeds.
 * The range is contiguous, but may cross adjacent LoaderCode/LoaderData
 * descriptors. Reject any other memory type, including conventional,
 * boot services, ACPI, runtime, MMIO, or an unaccounted hole.
 */
static int k0_loaded_image_bounds(const K0_EFI_LOADED_IMAGE *proto,
                                  const void *memory_map, K_U64 map_size,
                                  K_U64 descriptor_size, K_U32 version,
                                  K_U64 entry, K0_LOADED_IMAGE_BOUNDS *out) {
    if (!proto || !memory_map || !out || version != 1 ||
        !descriptor_size || descriptor_size < sizeof(K0_MEMORY_DESCRIPTOR) ||
        (descriptor_size & 7ULL) || !map_size ||
        map_size > K0_MEMORY_MAP_LIMIT || map_size % descriptor_size)
        return 0;
    K_U64 base = (K_U64)(unsigned long long)proto->image_base;
    K_U64 size = proto->image_size;
    if (proto->revision < 0x1000U || !size ||
        size > K0_PE_WX_MAX_IMAGE_BYTES ||
        (size & (K0_PAGE_SIZE - 1ULL)) ||
        base < 0x100000ULL ||
        (base & (K0_PAGE_SIZE - 1ULL)) ||
        base > 0x40000000ULL - size || /* QEMU-only low identity limit */
        entry < base || entry - base >= size)
        return 0;

    const K_U8 *map = (const K_U8 *)memory_map;
    const K_U64 count = map_size / descriptor_size;
    const K_U64 end = base + size;
    K_U64 cursor = base;
    K_U32 covered = 0;
    for (K_U64 step = 0; step < count && cursor < end; ++step) {
        int found = 0;
        for (K_U64 i = 0; i < count; ++i) {
            K0_MEMORY_DESCRIPTOR d =
                k0_read_descriptor(map + i * descriptor_size);
            if ((d.type != 1U && d.type != 2U) ||
                !d.number_of_pages ||
                d.number_of_pages > ~(K_U64)0 / K0_PAGE_SIZE ||
                d.physical_start > ~(K_U64)0 - d.number_of_pages * K0_PAGE_SIZE)
                continue;
            K_U64 desc_end = d.physical_start +
                             d.number_of_pages * K0_PAGE_SIZE;
            if (d.physical_start <= cursor && cursor < desc_end) {
                cursor = desc_end < end ? desc_end : end;
                ++covered;
                found = 1;
                break;
            }
        }
        if (!found) return 0;
    }
    if (cursor != end || !covered) return 0;
    K0_LOADED_IMAGE_BOUNDS next = {base, size, entry, covered};
    *out = next;
    return 1;
}
#endif
