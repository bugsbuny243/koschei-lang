#ifndef KOSCHEI_K0_LIVE_IMAGE_4K_WX_H
#define KOSCHEI_K0_LIVE_IMAGE_4K_WX_H
/*
 * QEMU-ONLY: split at most two 2MiB low identity PDEs that intersect the
 * actual loaded PE into 4KiB supervisor PTEs. No other executable huge PDE
 * is tolerated. RX image code is not writable, image data/header RW+NX,
 * readonly PE sections RO+NX; unclassified image holes are nonpresent.
 * Non-image pages in these windows remain RW+NX transition mappings.
 *
 * Not production isolation: unrelated RAM and firmware ranges retain
 * overbroad RW+NX identity mappings, external runtime reservations and
 * full exception policy are absent. This helper does not activate CR3.
 * All rejection checks precede any table writes (fail-closed).
 */
#include "paging_pe_section_wx.h"

#define K0_LIVE_WX_LOW_LIMIT 0x40000000ULL
#define K0_LIVE_WX_HUGE_SIZE 0x200000ULL
#define K0_LIVE_WX_NX (1ULL << 63)
#define K0_LIVE_WX_PDE_RW 0x83ULL
#define K0_LIVE_WX_PTE_RW 0x3ULL
#define K0_LIVE_WX_PTE_RO 0x1ULL
#define K0_LIVE_WX_MAX_SPLITS 2U

typedef struct {
    K_U32 split_count;
    K_U32 slot[2];
    K_U32 rx_pages;
    K_U32 writable_pages;
} K0_LIVE_WX_RECEIPT;

static int k0_live_image_4k_build(volatile K_U64 *pd,
                                   volatile K_U64 *pt0,
                                   volatile K_U64 *pt1,
                                   K_U64 frame0, K_U64 frame1,
                                   K_U64 image_base,
                                   const K0_PE_WX_LAYOUT *layout,
                                   K_U64 stack_address,
                                   const K_U64 *code_addresses,
                                   K_U32 code_count,
                                   K0_LIVE_WX_RECEIPT *result) {
    if (!pd || !pt0 || !pt1 || !result || !layout ||
        !code_addresses || !code_count || code_count > 16U ||
        !k0_pe_wx_identity_range(image_base, layout) ||
        !layout->page_count || !layout->executable_pages ||
        !layout->writable_pages || !stack_address ||
        stack_address >= K0_LIVE_WX_LOW_LIMIT ||
        (frame0 & (K0_PAGE_SIZE - 1ULL)) ||
        (frame1 & (K0_PAGE_SIZE - 1ULL)) ||
        frame0 < 0x100000ULL || frame1 < 0x100000ULL ||
        frame0 >= K0_LIVE_WX_LOW_LIMIT ||
        frame1 >= K0_LIVE_WX_LOW_LIMIT ||
        frame0 == frame1) return 0;

    K_U64 image_end = image_base + layout->image_size;
    if (image_end > K0_LIVE_WX_LOW_LIMIT - K0_LIVE_WX_HUGE_SIZE ||
        (stack_address >= image_base && stack_address < image_end) ||
        (frame0 >= image_base && frame0 < image_end) ||
        (frame1 >= image_base && frame1 < image_end) ||
        (frame0 >> 12) == (stack_address >> 12) ||
        (frame1 >> 12) == (stack_address >> 12))
        return 0;

    K_U32 first = (K_U32)(image_base >> 21);
    K_U32 last = (K_U32)((image_end - 1ULL) >> 21);
    K_U32 splits = last - first + 1U;
    if (!splits || splits > K0_LIVE_WX_MAX_SPLITS || last >= 511U)
        return 0;
    K_U32 observed_rx = 0, observed_rw = 0;
    for (K_U32 i = 0; i < layout->page_count; ++i) {
        K_U8 klass = layout->pages[i];
        if (klass == K0_PE_WX_CODE_RX) ++observed_rx;
        else if (klass == K0_PE_WX_DATA_RW_NX) ++observed_rw;
        else if (klass != K0_PE_WX_HEADERS_RW_NX &&
                 klass != K0_PE_WX_READ_RO_NX && klass != 0)
            return 0;
    }
    if (observed_rx != layout->executable_pages ||
        observed_rw != layout->writable_pages) return 0;
    for (K_U32 i = 0; i < code_count; ++i) {
        if (code_addresses[i] < image_base ||
            code_addresses[i] >= image_end ||
            layout->pages[(code_addresses[i] - image_base) / K0_PAGE_SIZE]
               != K0_PE_WX_CODE_RX)
            return 0;
    }
    /* Only the image's one or two split PDEs may be executable. All
     * remaining identity huge-page entries must already have NX set.
     */
    for (K_U32 i = 0; i < 512U; ++i) {
        if (i == first || (splits == 2U && i == last)) {
            if ((pd[i] & ~K0_LIVE_WX_NX) !=
                (((K_U64)i << 21) | K0_LIVE_WX_PDE_RW))
                return 0;
        } else if ((pd[i] & 0x81ULL) == 0x81ULL &&
                   !(pd[i] & K0_LIVE_WX_NX))
            return 0;
    }
    /* No checks after first write. Initialize PTEs before PDE attachment. */
    volatile K_U64 *pts[2] = {pt0, pt1};
    const K_U64 frames[2] = {frame0, frame1};
    for (K_U32 n = 0; n < splits; ++n) {
        K_U32 slot = first + n;
        for (K_U32 j = 0; j < 512U; ++j) {
            K_U64 physical = ((K_U64)slot << 21) +
                             (K_U64)j * K0_PAGE_SIZE;
            K_U64 entry = physical | K0_LIVE_WX_PTE_RW |
                          K0_LIVE_WX_NX;
            if (physical >= image_base && physical < image_end) {
                K_U8 klass = layout->pages[(physical - image_base) /
                                            K0_PAGE_SIZE];
                if (klass == K0_PE_WX_CODE_RX)
                    entry = physical | K0_LIVE_WX_PTE_RO;
                else if (klass == K0_PE_WX_READ_RO_NX)
                    entry = physical | K0_LIVE_WX_PTE_RO | K0_LIVE_WX_NX;
                else if (klass == 0)
                    entry = 0;
            }
            pts[n][j] = entry;
        }
    }
    for (K_U32 n = 0; n < splits; ++n)
        pd[first+n] = frames[n] | 3ULL; /* 4KiB PT, not PS huge PDE */
    result->split_count = splits;
    result->slot[0] = first;
    result->slot[1] = splits == 2U ? last : 0;
    result->rx_pages = observed_rx;
    result->writable_pages = observed_rw;
    return 1;
}
#endif
