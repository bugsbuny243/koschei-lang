#include "paging_gdt_4k.h"
#include <assert.h>
#include <stdio.h>

static K0_IDENTITY_OWNER_PLAN owner;
static K0_PAGE_POOL pool;
static K_U64 pd[512], pt0[512], pt1[512];
static K_U64 existing[512] __attribute__((aligned(4096)));
static volatile K_U64 *buffers[2]={pt0,pt1};
static K_U64 all[15], frames[2], gdt_target;
static void setup(void) {
    K0_MEMORY_PLAN plan={0,0,0x100000ULL,K0_PLAN_PAGES};
    pool=(K0_PAGE_POOL){0};
    assert(k0_pool_init(&pool,&plan,1));
    for (K_U32 i=0;i<15;++i)
        assert(k0_pool_claim(&pool,&all[i]));
    frames[0]=all[13];frames[1]=all[14];
    owner=(K0_IDENTITY_OWNER_PLAN){0};
    owner.firmware_gdt_base=0x600100ULL;
    for (K_U32 i=0;i<512;++i) {
        pd[i]=((K_U64)i<<21)|0x83ULL|K0_GDT_4K_NX;
        pt0[i]=0xbad00ULL;
        pt1[i]=0xbad00ULL;
        existing[i]=0;
        owner.allowed[i]=1;
    }
    gdt_target=0xdeadbeefULL;
}
static int run(K_U64 base,K_U64 bytes) {
    return k0_gdt_4k_build(pd,&pool,&owner,base,bytes,
                            all,15,frames,buffers,&gdt_target);
}
static void reject(K_U64 base,K_U64 bytes) {
    K_U64 before=pd[3], a=pt0[0], b=pt1[0], target=gdt_target;
    assert(!run(base,bytes));
    assert(pd[3]==before && pt0[0]==a && pt1[0]==b &&
           gdt_target==target);
}
int main(void) {
    K0_MEMORY_DESCRIPTOR map[]={{7,0,0x100000ULL,0,16,0}};
    K0_MEMORY_PLAN plan={0};
    assert(k0_memory_validate_plan(map,sizeof(map),sizeof(map[0]),1,&plan));
    K0_IDENTITY_OWNER_PLAN dummy={0};
    assert(!k0_identity_owner_plan(0,0,0,0,0,0,0,0,0,0,0,0,0,0,&dummy));
    assert(!k0_stack_guard_build(0,&dummy,0,0,0,0,0,0,0,0,0));
    assert(!k0_pool_4k_build(0,&pool,&dummy,0,0,0,0,0,0,0,0,0));

    setup();
    assert(run(0x600100ULL,0x40ULL));
    assert(gdt_target==0x600100ULL);
    assert(pd[3]==(frames[0]|3ULL));
    assert(pt0[0]==(0x600000ULL|K0_GDT_4K_RO_NX));
    assert(pt0[1]==0);
    assert(pt0[15]==0);
    assert(pd[2]==(0x400000ULL|0x83ULL|K0_GDT_4K_NX));

    setup();
    /* Synthetic host pointers are NOT claimed physical frames. Reject
     * them before dereferencing their page-table contents.
     */
    existing[0]=0x600000ULL|K0_GDT_4K_RO_NX;
    K_U64 address=(K_U64)(unsigned long long)&existing[0];
    pd[3]=address|3ULL;
    reject(0x600100ULL,0x40ULL);
    setup();
    existing[0]=0x600000ULL|3ULL|K0_GDT_4K_NX;
    address=(K_U64)(unsigned long long)&existing[0];
    pd[3]=address|3ULL;
    reject(0x600100ULL,0x40ULL);

    setup(); owner.allowed[3]=0;reject(0x600100ULL,0x40ULL);
    setup(); owner.firmware_gdt_base=0x600200ULL;
    reject(0x600100ULL,0x40ULL);
    setup(); pool.epoch=0;reject(0x600100ULL,0x40ULL);
    setup(); pool.claimed^=1U;reject(0x600100ULL,0x40ULL);
    setup(); frames[1]=frames[0];reject(0x600100ULL,0x40ULL);
    setup(); frames[1]=all[14]+K0_PAGE_SIZE;reject(0x600100ULL,0x40ULL);
    setup(); pd[3]=0;reject(0x600100ULL,0x40ULL);
    setup(); pd[3]=0x600083ULL;reject(0x600100ULL,0x40ULL);
    setup(); reject(0x600100ULL,0);
    setup(); reject(0x600100ULL,0x1001ULL);
    setup(); reject(0x3fffff00ULL,0x200ULL);

    /* Validate crossing a 2MiB boundary with two distinct new PT pages. */
    setup();
    owner.firmware_gdt_base=0x5ffff0ULL;
    assert(run(0x5ffff0ULL,0x40ULL));
    assert(pd[2]==frames[0]+3ULL && pd[3]==frames[1]+3ULL);
    assert(pt0[511]==(0x5ff000ULL|K0_GDT_4K_RO_NX));
    assert(pt1[0]==(0x600000ULL|K0_GDT_4K_RO_NX));

    setup();
    assert(k0_pool_release(&pool,all[14]));
    reject(0x600100ULL,0x40ULL);
    K_U64 reclaimed=0;
    assert(k0_pool_claim(&pool,&reclaimed)&&reclaimed==all[14]);
    assert(run(0x600100ULL,0x40ULL));
    puts("KOSCHEI-K0 GDT-4K-RO/1 PASS (PT data and strict ownership)");
    return 0;
}
