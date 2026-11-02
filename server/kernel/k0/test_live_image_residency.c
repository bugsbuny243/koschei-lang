#include "live_image_residency.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static K0_MEMORY_DESCRIPTOR memory[] = {
    {7, 0, 0x200000ULL, 0, 128, 0},
    {1, 0, 0x400000ULL, 0, 16, 0},
    {2, 0, 0x500000ULL, 0, 16, 0},
    {3, 0, 0x600000ULL, 0, 8, 0},
    {4, 0, 0x700000ULL, 0, 16, 0},
    {5, 0, 0x800000ULL, 0, 16, (1ULL << 63)},
    {11, 0, 0xfec00000ULL, 0, 4, 0},
};
#define MEMORY_SIZE sizeof(memory)
#define STRIDE sizeof(memory[0])
static int allowed(const K0_MEMORY_DESCRIPTOR *map, K_U64 size, K_U64 stride,
                   K_U32 version, K_U64 base, K_U64 image_size,
                   K_U64 rip, K_U64 rsp, K_U64 pool) {
    return k0_live_image_residency_preflight(map,size,stride,version,
             base,image_size,rip,rsp,pool);
}
#define CHECK_DENIED(change) do {                                  \
    K0_MEMORY_DESCRIPTOR tampered[sizeof(memory)/sizeof(memory[0])];\
    memcpy(tampered,memory,sizeof(memory));                         \
    change;                                                         \
    assert(!allowed(tampered,sizeof(tampered),STRIDE,1,              \
                    0x400000,0x10000,0x401200,0x701ff0,0x200000)); \
    assert(allowed(memory,MEMORY_SIZE,STRIDE,1,                      \
                   0x400000,0x10000,0x401200,0x701ff0,0x200000));  \
} while(0)

int main(void) {
    assert(allowed(memory,MEMORY_SIZE,STRIDE,1,
                   0x400000,0x10000,0x401200,0x701ff0,0x200000));
    assert(!allowed(0,MEMORY_SIZE,STRIDE,1,
                    0x400000,0x10000,0x401200,0x701ff0,0x200000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,2,
                    0x400000,0x10000,0x401200,0x701ff0,0x200000));
    assert(!allowed(memory,MEMORY_SIZE-1,STRIDE,1,
                    0x400000,0x10000,0x401200,0x701ff0,0x200000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0,0x10000,0x401200,0x701ff0,0x200000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400001,0x10000,0x401200,0x701ff0,0x200000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400000,0,0x401200,0x701ff0,0x200000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400000,0x10000,0x500000,0x701ff0,0x200000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400000,0x10000,0x3fffff,0x701ff0,0x200000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400000,0x10000,0x401200,0,0x200000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400000,0x10000,0x401200,0x201000,0x200000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400000,0x10000,0x401200,0x701ff0,0x201000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400000,0x10000,0x401200,0x701ff0,0x900000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400000,0x10000,0x401200,0x701ff0,0x400000));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400000,0x10000,0x401200,0x701ff0,0));
    assert(!allowed(memory,MEMORY_SIZE,STRIDE,1,
                    0x400000,K0_LIVE_IMAGE_MAX_SIZE+1,0x401200,0x701ff0,0x200000));
    CHECK_DENIED(tampered[1].type=2);
    CHECK_DENIED(tampered[1].type=11);
    CHECK_DENIED(tampered[1].number_of_pages=1);
    CHECK_DENIED(tampered[1].attributes=(1ULL << 63));
    CHECK_DENIED(tampered[4].type=1);
    CHECK_DENIED(tampered[4].type=5);
    CHECK_DENIED(tampered[4].attributes=(1ULL << 63));
    CHECK_DENIED(tampered[4].physical_start=0x710000ULL);
    CHECK_DENIED(tampered[0].type=11);
    CHECK_DENIED(tampered[0].attributes=(1ULL << 63));
    CHECK_DENIED(tampered[2].number_of_pages=0);
    CHECK_DENIED(tampered[6].physical_start=0x400000ULL);
    puts("KOSCHEI-K0 LIVE-IMAGE-RESIDENCY/1 PASS (model + validated map; no CR3 write)");
    return 0;
}
