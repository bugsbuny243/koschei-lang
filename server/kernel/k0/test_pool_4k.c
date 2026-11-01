#include "paging_pool_4k.h"
#include <assert.h>
#include <stdio.h>

static K0_PAGE_POOL pool;
static K0_IDENTITY_OWNER_PLAN owner;
static K_U64 pd[512], a[512], b[512];
static volatile K_U64 *buffers[2]={a,b};
static K_U64 all[13], frames[2];
static K_U64 missing;
static void init(K_U64 base) {
    K0_MEMORY_PLAN plan={0,0,base,K0_PLAN_PAGES};
    pool=(K0_PAGE_POOL){0};
    assert(k0_pool_init(&pool,&plan,1));
    for (K_U32 i=0;i<13;++i) assert(k0_pool_claim(&pool,&all[i]));
    frames[0]=all[11];frames[1]=all[12];
    owner=(K0_IDENTITY_OWNER_PLAN){0};
    owner.stack_floor=0x41c000ULL;
    owner.stack_end=0x421000ULL;
    for (K_U32 i=0;i<512;++i) {
        owner.allowed[i]=1;
        pd[i]=((K_U64)i<<21)|0x83ULL|K0_POOL_4K_NX;
        a[i]=0xbad000ULL;
        b[i]=0xbad000ULL;
    }
    missing=0xdeadbeefULL;
}
static int run(K_U64 gdt) {
    return k0_pool_4k_build(pd,&pool,&owner,
        0x800000ULL,0x10000ULL,gdt,0x40ULL,
        all,13,frames,buffers,&missing);
}
static void rejected(K_U64 gdt) {
    K_U64 pde=pd[0], left=a[0], right=b[0], witness=missing;
    assert(!run(gdt));
    assert(pd[0]==pde && a[0]==left && b[0]==right &&
           missing==witness);
}
int main(void) {
    /* Exercise transitive static symbols in freestanding strict -Werror
     * fixture; all are guaranteed fail-closed without physical derefs.
     */
    K0_IDENTITY_OWNER_PLAN dummy={0};
    assert(!k0_identity_owner_plan(0,0,0,0,0,0,0,0,0,0,0,0,0,0,&dummy));
    assert(!k0_stack_guard_build(0,&dummy,0,0,0,0,0,0,0,0,0));
    K0_MEMORY_DESCRIPTOR descriptors[] = {
      {7,0,0x100000ULL,0,16,0}
    };
    K0_MEMORY_PLAN validated={0};
    assert(k0_memory_validate_plan(descriptors,sizeof(descriptors),
                                   sizeof(descriptors[0]),1,&validated));
    init(0x100000ULL);
    assert(run(0x600100ULL));
    assert(missing==0x10d000ULL);
    assert(pd[0]==(frames[0]|3ULL));
    assert(a[(0x100000ULL>>12)&511ULL] ==
           (0x100000ULL|K0_POOL_4K_RW_NX));
    assert(a[(missing>>12)&511ULL]==0);
    assert(a[(0x180000ULL>>12)&511ULL]==0);
    assert(pd[1]==(0x200000ULL|0x83ULL|K0_POOL_4K_NX));

    init(0x100000ULL);
    assert(run(0x180100ULL)); /* GDT shares pool's 2MiB PDE */
    assert(a[(0x180000ULL>>12)&511ULL] ==
           (0x180000ULL|K0_POOL_4K_RO_NX));

    init(0x1fe000ULL);
    assert(run(0x600100ULL));
    assert(pd[0]==(frames[0]|3ULL));
    assert(pd[1]==(frames[1]|3ULL));
    assert(a[(0x1fe000ULL>>12)&511ULL] ==
           (0x1fe000ULL|K0_POOL_4K_RW_NX));
    assert(b[(0x200000ULL>>12)&511ULL] ==
           (0x200000ULL|K0_POOL_4K_RW_NX));
    assert(b[(missing>>12)&511ULL]==0);

    init(0x100000ULL);pd[0]=0;rejected(0x600100ULL);
    init(0x100000ULL);pd[0]=0x100003ULL;rejected(0x600100ULL);
    init(0x100000ULL);owner.allowed[0]=0;rejected(0x600100ULL);
    init(0x100000ULL);pool.claimed^=1U;rejected(0x600100ULL);
    init(0x100000ULL);pool.epoch=0;rejected(0x600100ULL);
    init(0x100000ULL);frames[1]=frames[0];rejected(0x600100ULL);
    init(0x100000ULL);frames[1]=all[13-1]+K0_PAGE_SIZE;
    rejected(0x600100ULL);
    init(0x100000ULL);owner.stack_floor=0x101000ULL;
    owner.stack_end=0x106000ULL;rejected(0x600100ULL);
    init(0x100000ULL);rejected(0x100100ULL); /* GDT inside pool */
    init(0x100000ULL);pool.active=K0_PLAN_PAGES;
    rejected(0x600100ULL);
    init(0x1fe000ULL);pd[1]=0;rejected(0x600100ULL);
    init(0x1fe000ULL);owner.stack_floor=0x200000ULL;
    owner.stack_end=0x205000ULL;rejected(0x600100ULL);

    /* Use each static page-pool helper under strict -Werror host build. */
    init(0x100000ULL);
    assert(k0_pool_release(&pool,all[12]));
    assert(!run(0x600100ULL));
    K_U64 recycled=0;
    assert(k0_pool_claim(&pool,&recycled)&&recycled==all[12]);
    assert(run(0x600100ULL));
    puts("KOSCHEI-K0 POOL-4K-CLAIMED/1 PASS (PT construction only)");
    return 0;
}
