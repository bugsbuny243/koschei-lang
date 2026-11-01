#ifndef KOSCHEI_K0_PE_SECTION_WX_H
#define KOSCHEI_K0_PE_SECTION_WX_H
/*
 * K0.4 W^X preflight of a *mapped* PE32+ EFI image. Data-only policy:
 * no CR3 changes, no permission activation, no firmware calls.
 *
 * Reject ambiguous 4 KiB ownership, execute+write, unreadable sections,
 * out-of-bounds ranges and malformed headers. Page flags refer to image
 * offsets (not a live address-space grant). Host-validated only until
 * loaded-image protocol acquisition and actual 4KiB PT mapping exist.
 */
#include "memory_map.h"

#define K0_PE_WX_MAX_IMAGE_BYTES (2ULL * 1024ULL * 1024ULL)
#define K0_PE_WX_MAX_PAGES (K0_PE_WX_MAX_IMAGE_BYTES / K0_PAGE_SIZE)
#define K0_PE_WX_MAX_SECTIONS 16U
#define K0_PE_WX_HEADERS_RW_NX 1U
#define K0_PE_WX_CODE_RX 2U
#define K0_PE_WX_READ_RO_NX 3U
#define K0_PE_WX_DATA_RW_NX 4U

typedef struct {
    K_U64 image_size;
    K_U32 page_count;
    K_U32 section_count;
    K_U32 executable_pages;
    K_U32 writable_pages;
    K_U8 pages[K0_PE_WX_MAX_PAGES];
} K0_PE_WX_LAYOUT;

typedef unsigned short K0_PE_U16;
static K0_PE_U16 k0_pe_wx_u16(const K_U8 *p) {
    return (K0_PE_U16)((K0_PE_U16)p[0] |
                        ((K0_PE_U16)p[1] << 8));
}
static K_U32 k0_pe_wx_u32(const K_U8 *p) {
    return (K_U32)p[0] | ((K_U32)p[1] << 8) |
           ((K_U32)p[2] << 16) | ((K_U32)p[3] << 24);
}
/* Cap the read extent before any pointer arithmetic; no partial commit. */
static int k0_pe_wx_parse(const void *mapped, K_U64 mapped_bytes,
                          K0_PE_WX_LAYOUT *out) {
    if (!mapped || !out || mapped_bytes < 0x200ULL ||
        mapped_bytes > K0_PE_WX_MAX_IMAGE_BYTES) return 0;
    const K_U8 *p = (const K_U8 *)mapped;
    if (k0_pe_wx_u16(p) != 0x5a4dU) return 0;
    K_U64 pe = k0_pe_wx_u32(p + 0x3c);
    if (pe > mapped_bytes - 24ULL || k0_pe_wx_u32(p + pe) != 0x4550U)
        return 0;
    K_U64 coff = pe + 4ULL;
    K_U32 sections = k0_pe_wx_u16(p + coff + 2ULL);
    K_U64 optional_size = k0_pe_wx_u16(p + coff + 16ULL);
    K_U64 optional = coff + 20ULL;
    if (k0_pe_wx_u16(p + coff) != 0x8664U ||
        sections == 0 || sections > K0_PE_WX_MAX_SECTIONS ||
        optional_size < 112ULL || optional_size > mapped_bytes - optional)
        return 0;
    if (k0_pe_wx_u16(p + optional) != 0x20bU ||
        k0_pe_wx_u16(p + optional + 68ULL) != 10U ||
        k0_pe_wx_u32(p + optional + 32ULL) != 4096U)
        return 0;
    K_U64 image_size = k0_pe_wx_u32(p + optional + 56ULL);
    K_U64 header_size = k0_pe_wx_u32(p + optional + 60ULL);
    if (!image_size || image_size != mapped_bytes ||
        image_size % K0_PAGE_SIZE || !header_size ||
        header_size > image_size)
        return 0;
    K_U64 table = optional + optional_size;
    if (table > mapped_bytes ||
        sections > (mapped_bytes - table) / 40ULL ||
        table + sections * 40ULL > header_size)
        return 0;
    K0_PE_WX_LAYOUT next;
    next.image_size = image_size;
    next.page_count = (K_U32)(image_size / K0_PAGE_SIZE);
    next.section_count = sections;
    next.executable_pages = 0;
    next.writable_pages = 0;
    for (K_U32 i = 0; i < K0_PE_WX_MAX_PAGES; ++i)
        next.pages[i] = 0; /* freestanding: avoid hidden memset import */
    K_U64 header_pages = (header_size + K0_PAGE_SIZE - 1ULL) / K0_PAGE_SIZE;
    for (K_U64 i = 0; i < header_pages; ++i)
        next.pages[i] = K0_PE_WX_HEADERS_RW_NX;

    for (K_U32 s = 0; s < sections; ++s) {
        const K_U8 *section = p + table + (K_U64)s * 40ULL;
        K_U64 virtual_bytes = k0_pe_wx_u32(section + 8);
        K_U64 virtual_start = k0_pe_wx_u32(section + 12);
        K_U64 raw_bytes = k0_pe_wx_u32(section + 16);
        K_U32 flags = k0_pe_wx_u32(section + 36);
        if (raw_bytes > virtual_bytes) virtual_bytes = raw_bytes;
        if (!virtual_bytes || (virtual_start & (K0_PAGE_SIZE - 1ULL)) ||
            virtual_start >= image_size ||
            virtual_bytes > image_size - virtual_start)
            return 0;
        int execute = (flags & 0x20000000U) != 0;
        int read = (flags & 0x40000000U) != 0;
        int write = (flags & 0x80000000U) != 0;
        if (!read || (execute && write)) return 0;
        K_U8 permission = execute ? K0_PE_WX_CODE_RX :
                          write ? K0_PE_WX_DATA_RW_NX : K0_PE_WX_READ_RO_NX;
        K_U64 pages = (virtual_bytes + K0_PAGE_SIZE - 1ULL) / K0_PAGE_SIZE;
        K_U64 first = virtual_start / K0_PAGE_SIZE;
        if (pages > next.page_count - first) return 0;
        for (K_U64 k = 0; k < pages; ++k) {
            if (next.pages[first + k]) return 0; /* even same-flags overlap */
            next.pages[first + k] = permission;
            if (execute) ++next.executable_pages;
            if (write) ++next.writable_pages;
        }
    }
    if (!next.executable_pages || !next.writable_pages) return 0;
    *out = next;
    return 1;
}

/* Physically enforce image bounds before any caller begins frame planning. */
static int k0_pe_wx_identity_range(K_U64 image_base,
                                    const K0_PE_WX_LAYOUT *layout) {
    return layout && layout->image_size &&
           layout->image_size <= K0_PE_WX_MAX_IMAGE_BYTES &&
           layout->page_count * K0_PAGE_SIZE == layout->image_size &&
           image_base >= 0x100000ULL &&
           !(image_base & (K0_PAGE_SIZE - 1ULL)) &&
           image_base <= 0x40000000ULL - layout->image_size;
}
#endif
