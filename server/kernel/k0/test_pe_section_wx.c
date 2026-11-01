#include "paging_pe_section_wx.h"
#include <assert.h>
#include <stdio.h>

static K_U8 image[0x7000];
static K0_PE_WX_LAYOUT layout;
static void put16(K_U32 pos, K_U32 value) {
    image[pos] = (K_U8)value;
    image[pos+1] = (K_U8)(value >> 8);
}
static void put32(K_U32 pos, K_U32 value) {
    for (K_U32 i=0; i<4; ++i) image[pos+i] = (K_U8)(value >> (8*i));
}
static void fixture(void) {
    for (K_U32 i=0; i<sizeof(image); ++i) image[i] = 0;
    put16(0, 0x5a4d);
    put32(0x3c, 0x80);
    put32(0x80, 0x4550);
    put16(0x84, 0x8664);
    put16(0x86, 3);
    put16(0x94, 0xf0);
    put16(0x98, 0x20b);
    put32(0x98+32, 4096);
    put32(0x98+56, sizeof(image));
    put32(0x98+60, 0x400);
    put16(0x98+68, 10);
    for (K_U32 n=0; n<3; ++n) {
        K_U32 sect=0x188+n*40;
        put32(sect+8, 0x800);
        put32(sect+12, (n+1)*4096);
        put32(sect+16, 0x600);
        put32(sect+36, n==0 ? 0x60000020U :
                          n==1 ? 0x40000040U : 0xc0000040U);
    }
}
static void reject_unchanged(void) {
    layout.page_count = 99;
    layout.pages[0] = 0xab;
    assert(!k0_pe_wx_parse(image,sizeof(image),&layout));
    assert(layout.page_count==99 && layout.pages[0]==0xab);
}
int main(void) {
    /* Reuse the UEFI validator symbol in strict -Werror builds. */
    K0_MEMORY_DESCRIPTOR descriptors[] = {{7,0,0x200000ULL,0,128,0},
                                           {3,0,0x100000ULL,0,256,0}};
    K0_MEMORY_PLAN memory = {0};
    assert(k0_memory_validate_plan(descriptors,sizeof(descriptors),
                                  sizeof(descriptors[0]),1,&memory));
    fixture();
    assert(k0_pe_wx_parse(image,sizeof(image),&layout));
    assert(layout.page_count==7 && layout.section_count==3);
    assert(layout.executable_pages==1 && layout.writable_pages==1);
    assert(layout.pages[0]==K0_PE_WX_HEADERS_RW_NX);
    assert(layout.pages[1]==K0_PE_WX_CODE_RX);
    assert(layout.pages[2]==K0_PE_WX_READ_RO_NX);
    assert(layout.pages[3]==K0_PE_WX_DATA_RW_NX);
    assert(layout.pages[4]==0);
    assert(k0_pe_wx_identity_range(0x200000ULL,&layout));
    assert(!k0_pe_wx_identity_range(0x200001ULL,&layout));
    assert(!k0_pe_wx_identity_range(0x3000ULL,&layout));
    assert(!k0_pe_wx_identity_range(0x40000000ULL,&layout));
    assert(k0_pe_wx_identity_range(0x40000000ULL-sizeof(image),&layout));
    assert(!k0_pe_wx_parse(image,sizeof(image)-1,&layout));
    assert(!k0_pe_wx_parse(image,0,&layout));
    assert(!k0_pe_wx_parse(0,sizeof(image),&layout));
    assert(!k0_pe_wx_parse(image,sizeof(image),0));

    fixture(); put32(0x3c,0xfffffff0U); reject_unchanged();
    fixture(); put16(0x84,0x14c); reject_unchanged();
    fixture(); put16(0x86,17); reject_unchanged();
    fixture(); put16(0x94,4); reject_unchanged();
    fixture(); put16(0x98,0x10b); reject_unchanged();
    fixture(); put16(0x98+68,2); reject_unchanged();
    fixture(); put32(0x98+32,512); reject_unchanged();
    fixture(); put32(0x98+56,0x10000); reject_unchanged();
    fixture(); put32(0x98+60,0x100); reject_unchanged();
    fixture(); put32(0x188+36,0xe0000020U); reject_unchanged(); /* W+X */
    fixture(); put32(0x188+36,0x20000020U); reject_unchanged(); /* no READ */
    fixture(); put32(0x188+12,0x2000); reject_unchanged(); /* overlap */
    fixture(); put32(0x188+12,0x1100); reject_unchanged(); /* unaligned */
    fixture(); put32(0x188+8,0xffffffffU); reject_unchanged();
    fixture(); put32(0x188+16,0xffffffffU); reject_unchanged();
    fixture(); put32(0x188+12,0x7000); reject_unchanged();
    fixture(); put16(0x86,0); reject_unchanged();
    fixture(); put16(0x86,2); /* no writable section */ reject_unchanged();
    fixture(); put32(0x188+36,0x40000040U); /* no executable section */
    reject_unchanged();
    puts("KOSCHEI-K0 PE-SECTION-WX/1 PASS (preflight only, no CPU mappings)");
    return 0;
}
