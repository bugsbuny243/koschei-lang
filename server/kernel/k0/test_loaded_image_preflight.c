#include "uefi_loaded_image_preflight.h"
#include <assert.h>
#include <stdio.h>

static K0_LOADED_IMAGE_BOUNDS bounds;
static K0_MEMORY_DESCRIPTOR map[] = {
    {1,0,0x200000ULL,0,4,0},
    {2,0,0x204000ULL,0,4,0},
    {7,0,0x300000ULL,0,32,0}
};
static K0_EFI_LOADED_IMAGE image = {0};
static void reset(void) {
    image.revision = 0x1000U;
    image.image_base = (void *)(unsigned long long)0x200000ULL;
    image.image_size = 0x7000ULL;
    map[0].type = 1;
    map[1].type = 2;
    map[0].physical_start = 0x200000ULL;
    map[1].physical_start = 0x204000ULL;
    map[0].number_of_pages = 4;
    map[1].number_of_pages = 4;
}
static void reject_untouched(K_U64 entry) {
    bounds.base = 77;
    bounds.descriptor_count = 88;
    assert(!k0_loaded_image_bounds(&image,map,sizeof(map),
                sizeof(map[0]),1,entry,&bounds));
    assert(bounds.base == 77 && bounds.descriptor_count == 88);
}
int main(void) {
    K0_MEMORY_PLAN physical = {0};
    /* Direct use of all static PE/GUID helpers in strict -Werror fixture. */
    K0_PE_WX_LAYOUT unused_pe = {0};
    assert(k0_loaded_image_guid.data1 == 0x5b1b31a1U);
    assert(!k0_pe_wx_parse(0, sizeof(map), &unused_pe));
    assert(!k0_pe_wx_identity_range(0, &unused_pe));
    reset();
    assert(k0_memory_validate_plan(map,sizeof(map),sizeof(map[0]),1,&physical));
    assert(k0_loaded_image_bounds(&image,map,sizeof(map),sizeof(map[0]),
                1,0x201000ULL,&bounds));
    assert(bounds.base == 0x200000ULL && bounds.size == 0x7000ULL &&
           bounds.entry == 0x201000ULL && bounds.descriptor_count == 2);

    reset(); image.revision = 0xfff; reject_untouched(0x201000ULL);
    reset(); image.image_base = (void *)(unsigned long long)0x200001ULL;
    reject_untouched(0x201000ULL);
    reset(); image.image_size = 0x7001; reject_untouched(0x201000ULL);
    reset(); image.image_size = K0_PE_WX_MAX_IMAGE_BYTES + K0_PAGE_SIZE;
    reject_untouched(0x201000ULL);
    reset(); image.image_base = (void *)(unsigned long long)0x3ffff000ULL;
    reject_untouched(0x201000ULL);
    reset(); reject_untouched(0x1fffffULL);
    reset(); reject_untouched(0x207000ULL);
    reset(); map[0].type = 7; reject_untouched(0x201000ULL);
    reset(); map[1].type = 3; reject_untouched(0x201000ULL);
    reset(); map[1].physical_start = 0x205000ULL; reject_untouched(0x201000ULL);
    reset(); map[0].number_of_pages = 0; reject_untouched(0x201000ULL);
    reset(); map[0].number_of_pages = ~(K_U64)0;
    reject_untouched(0x201000ULL);
    reset();
    assert(!k0_loaded_image_bounds(0,map,sizeof(map),sizeof(map[0]),
                1,0x201000ULL,&bounds));
    assert(!k0_loaded_image_bounds(&image,0,sizeof(map),sizeof(map[0]),
                1,0x201000ULL,&bounds));
    assert(!k0_loaded_image_bounds(&image,map,sizeof(map)-1,sizeof(map[0]),
                1,0x201000ULL,&bounds));
    assert(!k0_loaded_image_bounds(&image,map,sizeof(map),16,
                1,0x201000ULL,&bounds));
    assert(!k0_loaded_image_bounds(&image,map,sizeof(map),sizeof(map[0]),
                2,0x201000ULL,&bounds));
    assert(!k0_loaded_image_bounds(&image,map,sizeof(map),sizeof(map[0]),
                1,0x201000ULL,0));
    puts("KOSCHEI-K0 LOADED-IMAGE-BOUNDS/1 PASS (UEFI metadata only)");
    return 0;
}
