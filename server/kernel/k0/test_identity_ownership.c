#include "paging_identity_ownership.h"
#include <assert.h>
#include <stdio.h>

static K0_IDENTITY_OWNER_PLAN plan;
static K0_MEMORY_DESCRIPTOR map[] = {
    {7, 0, 0x100000ULL, 0, 16, 0},
    {1, 0, 0x200000ULL, 0, 16, 0},
    {4, 0, 0x400000ULL, 0, 64, 0},
    {3, 0, 0x600000ULL, 0, 8, 0}
};
static K_U64 frames[] = {0x100000ULL,0x101000ULL,0x102000ULL,
                         0x103000ULL,0x104000ULL};
static void reset(void) {
    map[0].type = 7;
    map[0].physical_start = 0x100000ULL;
    map[0].number_of_pages = 16;
    map[1].type = 1;
    map[1].physical_start = 0x200000ULL;
    map[1].number_of_pages = 16;
    map[2].type = 4;
    map[2].physical_start = 0x400000ULL;
    map[2].number_of_pages = 64;
    map[3].type = 3;
    map[3].physical_start = 0x600000ULL;
    map[3].number_of_pages = 8;
    frames[0] = 0x100000ULL;
    frames[1] = 0x101000ULL;
    frames[2] = 0x102000ULL;
    frames[3] = 0x103000ULL;
    frames[4] = 0x104000ULL;
}
static int check(K_U64 image_base,K_U64 image_bytes,
                 K_U64 pool_base,K_U64 pool_bytes,
                 K_U64 stack,K_U64 idt,K_U32 frame_count) {
    return k0_identity_owner_plan(map,sizeof(map),sizeof(map[0]),1,
        image_base,image_bytes,pool_base,pool_bytes,stack,idt,
        0x600100ULL, 0x40ULL, frames,frame_count,&plan);
}
static void unchanged(void) {
    assert(plan.mapped_slots == 99 && plan.allowed[0] == 0xa5);
}
static void reject(K_U64 ib,K_U64 is,K_U64 pb,K_U64 ps,
                   K_U64 stack,K_U64 idt,K_U32 fc) {
    plan.mapped_slots=99;
    plan.allowed[0]=0xa5;
    assert(!check(ib,is,pb,ps,stack,idt,fc));
    unchanged();
}
int main(void) {
    reset();
    assert(check(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
                 0x420800ULL,0x205000ULL,5));
    assert(plan.mapped_slots==4);
    assert(plan.allowed[0] && plan.allowed[1] && plan.allowed[2] &&
           plan.allowed[3]);
    assert(!plan.allowed[4] && !plan.allowed[128]);
    assert(plan.firmware_gdt_base==0x600100ULL);
    assert(!plan.allowed[510] && !plan.allowed[511]);
    assert(plan.stack_floor==0x41c000ULL && plan.stack_end==0x421000ULL);

    /* A matching address range is not proof of frame ownership. Require
     * the exact claimed bits and active count from the post-firmware pool.
     */
    K0_MEMORY_PLAN memory = {0};
    assert(k0_memory_validate_plan(map,sizeof(map),sizeof(map[0]),
                                   1,&memory));
    K0_PAGE_POOL pool={0};
    assert(!k0_pool_init(&pool,&memory,0));
    assert(k0_pool_init(&pool,&memory,1));
    assert(!k0_identity_owner_frames_match(&pool,frames,5));
    for (K_U32 i=0;i<5;++i) {
        K_U64 claimed=0;
        assert(k0_pool_claim(&pool,&claimed));
        assert(claimed==frames[i]);
    }
    assert(k0_identity_owner_frames_match(&pool,frames,5));
    frames[2]=frames[1];
    assert(!k0_identity_owner_frames_match(&pool,frames,5));
    frames[2]=0x102000ULL;
    assert(k0_pool_release(&pool,frames[2]));
    assert(!k0_identity_owner_frames_match(&pool,frames,5));
    K_U64 reclaimed=0;
    assert(k0_pool_claim(&pool,&reclaimed) && reclaimed==frames[2]);
    assert(k0_identity_owner_frames_match(&pool,frames,5));
    pool.claimed ^= 1U << 7;
    assert(!k0_identity_owner_frames_match(&pool,frames,5));
    pool.claimed ^= 1U << 7;
    pool.epoch=0;
    assert(!k0_identity_owner_frames_match(&pool,frames,5));
    reset();

    reset(); reject(0x200001ULL,0x10000ULL,0x100000ULL,0x10000ULL,
                    0x420800ULL,0x205000ULL,5);
    reset(); reject(0x200000ULL,0x10001ULL,0x100000ULL,0x10000ULL,
                    0x420800ULL,0x205000ULL,5);
    reset(); reject(0x200000ULL,0x10000ULL,0x100000ULL,0x8000ULL,
                    0x420800ULL,0x205000ULL,5);
    reset(); reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
                    0x420800ULL,0x500000ULL,5);
    reset(); reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
                    0x200010ULL,0x205000ULL,5);
    reset(); reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
                    0x100010ULL,0x205000ULL,5);
    reset(); map[1].type=3;
    reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
           0x420800ULL,0x205000ULL,5);
    reset(); map[2].type=7;
    reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
           0x420800ULL,0x205000ULL,5);
    reset(); map[2].physical_start=0x421000ULL;
    reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
           0x420800ULL,0x205000ULL,5);
    reset(); map[3].type=7;
    reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
           0x420800ULL,0x205000ULL,5);
    reset(); frames[2]=frames[1];
    reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
           0x420800ULL,0x205000ULL,5);
    reset(); frames[2]=0x300000ULL;
    reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
           0x420800ULL,0x205000ULL,5);
    reset(); frames[3]=0x100001ULL;
    reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
           0x420800ULL,0x205000ULL,5);
    reset(); reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
                    0x420800ULL,0x205000ULL,0);
    reset(); reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
                    0x420800ULL,0x205000ULL,17);
    reset(); reject(0x3fc00000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
                    0x420800ULL,0x3fc00000ULL,5);
    reset(); map[1].physical_start=0x100000ULL;
    reject(0x200000ULL,0x10000ULL,0x100000ULL,0x10000ULL,
           0x420800ULL,0x205000ULL,5);
    puts("KOSCHEI-K0 IDENTITY-OWNERSHIP/1 PASS (stack/PE/pool/GDT aperture)");
    return 0;
}
