#include "paging_live_image_4k_wx.h"
#include <assert.h>
#include <stdio.h>
static K_U64 pd[512], pt0[512], pt1[512];
static K0_PE_WX_LAYOUT layout;
static K0_LIVE_WX_RECEIPT result;

static void setup(K_U64 base, K_U64 bytes) {
    for (K_U32 i=0; i<512; ++i) {
        pd[i] = ((K_U64)i << 21) | 0x83ULL | K0_LIVE_WX_NX;
        pt0[i]=0xdeadbeefULL;
        pt1[i]=0xdeadbeefULL;
    }
    layout.image_size=bytes;
    layout.page_count=(K_U32)(bytes/K0_PAGE_SIZE);
    layout.section_count=2;
    layout.executable_pages=1;
    layout.writable_pages=1;
    for (K_U32 i=0; i<K0_PE_WX_MAX_PAGES; ++i) layout.pages[i]=0;
    layout.pages[0]=K0_PE_WX_HEADERS_RW_NX;
    layout.pages[1]=K0_PE_WX_CODE_RX;
    layout.pages[2]=K0_PE_WX_DATA_RW_NX;
    K_U32 first=(K_U32)(base>>21),last=(K_U32)((base+bytes-1)>>21);
    pd[first] &= ~K0_LIVE_WX_NX;
    pd[last] &= ~K0_LIVE_WX_NX;
    result.split_count=123;
}
static void unchanged(K_U64 base,K_U64 code) {
    K_U64 expected_code[]={code};
    assert(!k0_live_image_4k_build(pd,pt0,pt1,0x800000,0x801000,
                                   base,&layout,0x900000,expected_code,
                                   1,&result));
    assert(result.split_count==123);
    for (K_U32 i=0;i<512;++i)
        assert(pt0[i]==0xdeadbeefULL && pt1[i]==0xdeadbeefULL);
}
int main(void) {
    /* exercise bundled static helpers under native -Werror */
    K0_MEMORY_DESCRIPTOR memory[]={{7,0,0x400000,0,64,0}};
    K0_MEMORY_PLAN plan={0};
    assert(k0_memory_validate_plan(memory,sizeof(memory),sizeof(memory[0]),
                                    1,&plan));
    assert(!k0_pe_wx_parse(0,0,&layout));
    const K_U64 base=0x3ff000ULL,code[]={0x400000ULL};
    setup(base,0x4000ULL);
    assert(k0_live_image_4k_build(pd,pt0,pt1,0x800000,0x801000,
                                  base,&layout,0x900000,code,1,&result));
    assert(result.split_count==2 && result.slot[0]==1 &&
           result.slot[1]==2 && result.rx_pages==1 &&
           result.writable_pages==1);
    assert(pd[1]==0x800003ULL && pd[2]==0x801003ULL);
    assert(pt0[511]==(0x3ff000ULL|3ULL|K0_LIVE_WX_NX));
    assert(pt1[0]==(0x400000ULL|1ULL));
    assert(pt1[1]==(0x401000ULL|3ULL|K0_LIVE_WX_NX));
    assert(pt1[2]==0);
    assert(pd[3] & K0_LIVE_WX_NX);
    setup(base,0x4000ULL);
    layout.pages[1]=K0_PE_WX_DATA_RW_NX;
    unchanged(base,code[0]);
    setup(base,0x4000ULL);
    layout.pages[2]=K0_PE_WX_CODE_RX;
    unchanged(base,code[0]);
    setup(base,0x4000ULL);
    layout.pages[2]=0xff;
    unchanged(base,code[0]);
    setup(base,0x4000ULL);
    layout.executable_pages=0;
    unchanged(base,code[0]);
    setup(base,0x4000ULL);
    unchanged(base,0x500000ULL);
    setup(base,0x4000ULL);
    pd[17] &= ~K0_LIVE_WX_NX; /* unexpected huge RWX outside image */
    unchanged(base,code[0]);
    setup(base,0x4000ULL);
    layout.image_size=0x200001ULL; /* >2MiB, not 4K aligned */
    unchanged(base,code[0]);
    setup(base,0x4000ULL);
    layout.page_count=0;
    unchanged(base,code[0]);
    setup(base,0x4000ULL);
    result.split_count=123;
    assert(!k0_live_image_4k_build(pd,pt0,pt1,0x800001,0x801000,
                                   base,&layout,0x900000,code,1,&result));
    assert(result.split_count==123 && pt0[0]==0xdeadbeefULL);
    setup(base,0x4000ULL);
    assert(!k0_live_image_4k_build(pd,pt0,pt1,0x800000,0x801000,
                                   base, &layout,base+0x1000ULL,code,1,
                                   &result));
    assert(result.split_count==123);
    setup(0x400000ULL,0x3000ULL);
    const K_U64 one_code[]={0x401000ULL};
    assert(k0_live_image_4k_build(pd,pt0,pt1,0x800000,0x801000,
                                  0x400000ULL,&layout,0x900000,
                                  one_code,1,&result));
    assert(result.split_count==1 && result.slot[0]==2);
    assert(pd[2]==0x800003ULL && (pt0[1] & K0_LIVE_WX_NX)==0 &&
           (pt0[1] & 2ULL)==0);
    puts("KOSCHEI-K0 LIVE-IMAGE-4K-WX/1 PASS (PT planning, hardware gate separate)");
    return 0;
}
