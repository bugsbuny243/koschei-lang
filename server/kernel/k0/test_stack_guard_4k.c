#include "paging_stack_guard_4k.h"
#include <assert.h>
#include <stdio.h>

static K0_IDENTITY_OWNER_PLAN owner;
static K_U64 pd[512];
static K_U64 pt0[512];
static K_U64 pt1[512];
static volatile K_U64 *buffers[2] = {pt0, pt1};
static K_U64 frames[2] = {0x101000ULL, 0x102000ULL};
static K_U64 guard;
static K0_MEMORY_DESCRIPTOR map[] = {
    {7,0,0x100000ULL,0,16,0},
    {1,0,0x200000ULL,0,16,0},
    {4,0,0x400000ULL,0,64,0},
    {3,0,0x600000ULL,0,8,0}
};

static void setup(void) {
    /* Every hostile-case fixture starts from an independent valid owner
     * snapshot; stale frame mutation must not poison the next case.
     */
    frames[0]=0x101000ULL;
    frames[1]=0x102000ULL;
    K_U64 all_frames[2] = {frames[0],frames[1]};
    assert(k0_identity_owner_plan(map,sizeof(map),sizeof(map[0]),1,
          0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
          0x420800ULL,0x205000ULL,0x600100ULL,0x40ULL,
          all_frames,2,&owner));
    for (K_U32 i=0;i<512;++i)
        pd[i]=((K_U64)i<<21)|0x83ULL|K0_STACK_GUARD_NX;
    for (K_U32 i=0;i<512;++i) {
        pt0[i]=0xbaddcafeULL;
        pt1[i]=0xbaddcafeULL;
    }
    guard=0xdeadbeefULL;
}
static int install(void) {
    return k0_stack_guard_build(pd,&owner,
       0x200000ULL,0x10000ULL,
       0x100000ULL,0x10000ULL,
       0x600100ULL,0x40ULL,
       frames,buffers,&guard);
}
static void bad(void) {
    K_U64 old=pd[2], old0=pt0[0], old1=pt1[0];
    guard=0xdeadbeefULL;
    assert(!install());
    assert(guard==0xdeadbeefULL &&
           pd[2]==old && pt0[0]==old0 && pt1[0]==old1);
}
int main(void) {
    K0_MEMORY_PLAN valid={0};
    assert(k0_memory_validate_plan(map,sizeof(map),sizeof(map[0]),1,&valid));
    K0_PAGE_POOL pool={0};
    assert(k0_pool_init(&pool,&valid,1));
    K_U64 a=0,b=0;
    assert(k0_pool_claim(&pool,&a) && k0_pool_claim(&pool,&b));
    K_U64 claimed[2]={a,b};
    assert(k0_identity_owner_frames_match(&pool,claimed,2));
    assert(k0_pool_release(&pool,b));
    assert(!k0_identity_owner_frames_match(&pool,claimed,2));
    K_U64 recycled=0;
    assert(k0_pool_claim(&pool,&recycled) && recycled==b);
    assert(k0_identity_owner_frames_match(&pool,claimed,2));

    setup();
    assert(install());
    assert(guard==0x41b000ULL);
    assert(pd[2] == (frames[0]|3ULL));
    assert(pt0[(guard>>12)&511ULL]==0);
    assert(pt0[(0x41c000ULL>>12)&511ULL]==
           (0x41c000ULL|K0_STACK_GUARD_PTE_RW_NX));
    assert(pt0[(0x420000ULL>>12)&511ULL]==
           (0x420000ULL|K0_STACK_GUARD_PTE_RW_NX));
    assert(pt0[(0x421000ULL>>12)&511ULL]==0);
    assert(pt0[(0x430000ULL>>12)&511ULL]==0);
    assert(pt1[0]==0);
    assert(pd[1]==(0x200000ULL|0x83ULL|K0_STACK_GUARD_NX));

    setup(); owner.allowed[2]=0; bad();
    setup(); pd[2]=0; bad();
    setup(); pd[2]=0x400003ULL; bad(); /* existing split PT */
    setup(); owner.stack_floor=0x200000ULL; bad(); /* overlaps image */
    setup(); owner.stack_floor=0; bad();
    setup(); owner.stack_end=owner.stack_floor+K0_PAGE_SIZE; bad();
    setup(); frames[1]=frames[0]; bad();
    setup(); frames[1]=0x300000ULL; bad();
    setup(); frames[1]=0x102001ULL; bad();
    frames[1]=0x102000ULL;
    setup(); buffers[1]=buffers[0]; bad();
    buffers[1]=pt1;
    setup(); owner.stack_floor=0x1000ULL; bad();
    setup(); owner.stack_floor=0x3fc00000ULL;
    owner.stack_end=owner.stack_floor+5ULL*K0_PAGE_SIZE;
    bad();
    setup(); owner.stack_floor=0x41c000ULL;
    assert(!k0_stack_guard_build(0,&owner,0x200000ULL,0x10000ULL,
               0x100000ULL,0x10000ULL,0x600100ULL,0x40ULL,
               frames,buffers,&guard));
    setup(); owner.stack_floor=0x41c000ULL;
    assert(!k0_stack_guard_build(pd,0,0x200000ULL,0x10000ULL,
               0x100000ULL,0x10000ULL,0x600100ULL,0x40ULL,
               frames,buffers,&guard));
    setup(); owner.stack_floor=0x41c000ULL;
    assert(!k0_stack_guard_build(pd,&owner,0x200000ULL,0x10000ULL,
               0x100000ULL,0x10000ULL,0x41b000ULL,0x40ULL,
               frames,buffers,&guard)); /* GDT on guard */

    /* Synthetic two-PDE boundary: stack spans adjacent 2MiB windows,
     * and the real lower guard remains nonpresent after both PTs install.
     */
    setup();
    owner.stack_floor=0x5ff000ULL;
    owner.stack_end=0x604000ULL;
    owner.allowed[2]=1;
    owner.allowed[3]=1;
    assert(install());
    assert(guard==0x5fe000ULL);
    assert(pd[2]==frames[0]+3ULL && pd[3]==frames[1]+3ULL);
    assert(pt0[(0x5fe000ULL>>12)&511ULL]==0);
    assert(pt0[(0x5ff000ULL>>12)&511ULL]==
           (0x5ff000ULL|K0_STACK_GUARD_PTE_RW_NX));
    assert(pt1[0x40ULL/4ULL]==0); /* unrelated physical page not mapped */
    assert(pt1[(0x600000ULL>>12)&511ULL]==
           (0x600000ULL|K0_STACK_GUARD_PTE_RW_NX));
    puts("KOSCHEI-K0 STACK-GUARD-4K/1 PASS (real PT data; CPU proof separate)");
    return 0;
}
