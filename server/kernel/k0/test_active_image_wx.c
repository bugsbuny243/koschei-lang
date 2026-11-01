#include "paging_active_image_wx.h"
#include <assert.h>
#include <stdio.h>
static K0_PE_WX_LAYOUT layout;
static K0_LOADED_IMAGE_BOUNDS image;
static K_U64 pd[512];
static K_U64 frames[2] = {0x300000ULL,0x301000ULL};
static K_U64 codes[2] = {0x201010ULL,0x201ff0ULL};
static void setup(void) {
    image.base=0x200000ULL;
    image.size=0x7000ULL;
    image.entry=0x201010ULL;
    layout.image_size=image.size;
    layout.page_count=7;
    for (K_U32 i=0;i<512;++i) {
        pd[i]=((K_U64)i<<21)|0x83ULL|K0_IMAGE_WX_PTE_NX;
        layout.pages[i]=0;
    }
    layout.pages[0]=K0_PE_WX_HEADERS_RW_NX;
    layout.pages[1]=K0_PE_WX_CODE_RX;
    layout.pages[2]=K0_PE_WX_READ_RO_NX;
    layout.pages[3]=K0_PE_WX_DATA_RW_NX;
    layout.executable_pages=1;
    layout.writable_pages=1;
}
int main(void) {
    K0_MEMORY_DESCRIPTOR map[1]={{7,0,0x300000ULL,0,32,0}};
    K0_MEMORY_PLAN unused={0};
    assert(k0_memory_validate_plan(map,sizeof(map),sizeof(map[0]),1,&unused));
    /* Exercise all transitive static helpers under the strict -Werror
     * host build, without probing unowned physical memory addresses.
     */
    K0_EFI_LOADED_IMAGE protocol={0};
    K0_LOADED_IMAGE_BOUNDS rejected={0};
    assert(k0_loaded_image_guid.data1 == 0x5b1b31a1U);
    assert(!k0_loaded_image_bounds(&protocol,0,0,0,1,0,&rejected));
    assert(!k0_pe_wx_parse(0,0,&layout));
    assert(!k0_image_wx_activate_tables(0,&image,&layout,codes,2,
                                         0x450000,0x460000,frames));
    setup();
    assert(k0_image_wx_preflight(&image,&layout,codes,2,0x450000,0x460000,frames));
    assert(!k0_image_wx_preflight(0,&layout,codes,2,0x450000,0x460000,frames));
    assert(!k0_image_wx_preflight(&image,&layout,0,2,0x450000,0x460000,frames));
    assert(!k0_image_wx_preflight(&image,&layout,codes,0,0x450000,0x460000,frames));
    assert(!k0_image_wx_preflight(&image,&layout,codes,17,0x450000,0x460000,frames));
    assert(!k0_image_wx_preflight(&image,&layout,codes,2,0,0x460000,frames));
    image.entry=0x203000ULL;
    assert(!k0_image_wx_preflight(&image,&layout,codes,2,0x450000,0x460000,frames));
    image.entry=0x201010ULL;
    codes[1]=0x203000ULL;
    assert(!k0_image_wx_preflight(&image,&layout,codes,2,0x450000,0x460000,frames));
    codes[1]=0x201ff0ULL;
    assert(!k0_image_wx_preflight(&image,&layout,codes,2,0x201001,0x460000,frames));
    assert(!k0_image_wx_preflight(&image,&layout,codes,2,0x450000,0x201001,frames));
    frames[0]=image.base;
    assert(!k0_image_wx_preflight(&image,&layout,codes,2,0x450000,0x460000,frames));
    frames[0]=frames[1];
    assert(!k0_image_wx_preflight(&image,&layout,codes,2,0x450000,0x460000,frames));
    frames[0]=0x300000;
    image.base=0x3ffff000ULL;
    assert(!k0_image_wx_preflight(&image,&layout,codes,2,0x450000,0x460000,frames));
    image.base=0x200000ULL;
    layout.pages[1]=K0_PE_WX_DATA_RW_NX;
    assert(!k0_image_wx_preflight(&image,&layout,codes,2,0x450000,0x460000,frames));
    layout.pages[1]=K0_PE_WX_CODE_RX;
    assert(pd[1]==(0x200000ULL|0x83ULL|K0_IMAGE_WX_PTE_NX));
    /* The native preflight is side-effect free. Actual CPU live mapping and
     * write denial are proven only in the separate QEMU-only image.
     */
    puts("KOSCHEI-K0 ACTIVE-IMAGE-WX/1 PASS (preflight, QEMU CPU gate separate)");
    return 0;
}
