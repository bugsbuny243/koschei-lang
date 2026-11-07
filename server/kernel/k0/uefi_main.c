/*
 * Koschei Server K0: independent x86-64 UEFI boot PROBE, NOT a full kernel.
 * Freestanding: no hosted runtime, libc, Linux/Windows/Go/Python dependency.
 * This first slice owns its COM1 UART operations via x86 I/O ports.
 *
 * Firmware remains a boot dependency; this does NOT prove trusted firmware,
 * MMU isolation, canonical sealed MIR execution, or device-level effect gates.
 */
#include "memory_map.h"
#include "page_pool.h"
#include "paging_frame_probe.h"
typedef unsigned short K_U16;
typedef void *EFI_HANDLE;
typedef K_U64 EFI_STATUS;

typedef struct {
    K_U64 signature;
    K_U32 revision;
    K_U32 header_size;
    K_U32 crc32;
    K_U32 reserved;
} EFI_TABLE_HEADER;

typedef EFI_STATUS (__attribute__((ms_abi)) *EFI_GET_MEMORY_MAP)(
    K_U64 *map_size, void *map, K_U64 *map_key,
    K_U64 *descriptor_size, K_U32 *descriptor_version);
typedef EFI_STATUS (__attribute__((ms_abi)) *EFI_EXIT_BOOT_SERVICES)(
    EFI_HANDLE image, K_U64 map_key);
typedef struct {
    K_U32 data1;
    unsigned short data2, data3;
    K_U8 data4[8];
} K0_EFI_GUID;
_Static_assert(sizeof(K0_EFI_GUID) == 16, "EFI GUID is 128 bits");
typedef EFI_STATUS (__attribute__((ms_abi)) *EFI_HANDLE_PROTOCOL)(
    EFI_HANDLE image, K0_EFI_GUID *protocol, void **interface);


typedef struct {
    EFI_TABLE_HEADER hdr;
    void *raise_tpl;
    void *restore_tpl;
    void *allocate_pages;
    void *free_pages;
    EFI_GET_MEMORY_MAP get_memory_map;
    void *unclaimed_before_handle_protocol[11];
    EFI_HANDLE_PROTOCOL handle_protocol;
    void *unclaimed_after_handle_protocol[9];
    EFI_EXIT_BOOT_SERVICES exit_boot_services;
} EFI_BOOT_SERVICES_SLICE;

typedef struct {
    EFI_TABLE_HEADER hdr;
    K_U16 *firmware_vendor;
    K_U32 firmware_revision;
    EFI_HANDLE console_in_handle;
    void *con_in;
    EFI_HANDLE console_out_handle;
    void *con_out;
    EFI_HANDLE standard_error_handle;
    void *std_err;
    void *runtime_services;
    EFI_BOOT_SERVICES_SLICE *boot_services;
    K_U64 table_entries;
    void *configuration_table;
} EFI_SYSTEM_TABLE;

_Static_assert(sizeof(EFI_TABLE_HEADER) == 24, "UEFI table header");
_Static_assert(__builtin_offsetof(EFI_SYSTEM_TABLE, boot_services) == 96, "UEFI boot services offset");
_Static_assert(sizeof(EFI_SYSTEM_TABLE) == 120, "UEFI system table layout");
_Static_assert(__builtin_offsetof(EFI_BOOT_SERVICES_SLICE, get_memory_map) == 56,
               "UEFI GetMemoryMap ABI offset");
_Static_assert(__builtin_offsetof(EFI_BOOT_SERVICES_SLICE, handle_protocol) == 152,
               "UEFI HandleProtocol ABI offset");
_Static_assert(__builtin_offsetof(EFI_BOOT_SERVICES_SLICE, exit_boot_services) == 232,
               "UEFI ExitBootServices ABI offset");
#ifdef KOSCHEI_QEMU_PF_TEST
/* Diagnostics use the firmware LoadedImage protocol while Boot Services
 * are still available. No UEFI callbacks are used after ExitBootServices.
 */
typedef struct {
    K_U32 revision, pad_revision;
    EFI_HANDLE parent_handle;
    EFI_SYSTEM_TABLE *system_table;
    EFI_HANDLE device_handle;
    void *file_path, *reserved;
    K_U32 load_options_size, pad_load_options;
    void *load_options;
    void *image_base;
    K_U64 image_size;
    K_U32 image_code_type, image_data_type;
    void *unload;
} K0_EFI_LOADED_IMAGE;
_Static_assert(__builtin_offsetof(K0_EFI_LOADED_IMAGE, image_base) == 64,
               "LoadedImage ImageBase ABI offset");
_Static_assert(__builtin_offsetof(K0_EFI_LOADED_IMAGE, image_size) == 72,
               "LoadedImage ImageSize ABI offset");
static int k0_uefi_loaded_image_identity(EFI_HANDLE image,
                                          EFI_SYSTEM_TABLE *system,
                                          K_U64 *base, K_U64 *size) {
    K0_EFI_GUID guid = {
        0x5b1b31a1U, 0x9562U, 0x11d2U,
        {0x8eU, 0x3fU, 0x00U, 0xa0U, 0xc9U, 0x69U, 0x72U, 0x3bU}
    };
    K0_EFI_LOADED_IMAGE *loaded = 0;
    if (!system || !system->boot_services ||
        !system->boot_services->handle_protocol || !image ||
        system->boot_services->handle_protocol(image, &guid,
                                                (void **)&loaded) != 0 ||
        !loaded || loaded->system_table != system ||
        !loaded->image_base || !loaded->image_size ||
        (loaded->image_code_type != 1U && loaded->image_code_type != 3U) ||
        (loaded->image_data_type != 2U && loaded->image_data_type != 4U))
        return 0;
    *base = (K_U64)(unsigned long long)loaded->image_base;
    *size = loaded->image_size;
    return 1;
}
#endif
static K_U8 k0_map_buffer[K0_MEMORY_MAP_LIMIT] __attribute__((aligned(16)));
static K0_PAGE_POOL k0_pool;

static inline void port_out(K_U16 port, K_U8 value) {
    __asm__ __volatile__("outb %0, %1" : : "a"(value), "Nd"(port));
}
static inline K_U8 port_in(K_U16 port) {
    K_U8 value;
    __asm__ __volatile__("inb %1, %0" : "=a"(value) : "Nd"(port));
    return value;
}

#define COM1 0x3f8u
static void serial_init(void) {
    port_out(COM1 + 1, 0);      /* no UART interrupts */
    port_out(COM1 + 3, 0x80);   /* DLAB */
    port_out(COM1, 1);         /* divisor 1: 115200 baud */
    port_out(COM1 + 1, 0);
    port_out(COM1 + 3, 3);      /* 8N1 */
    port_out(COM1 + 2, 0xc7);   /* FIFO reset */
    port_out(COM1 + 4, 0x0b);   /* DTR, RTS, OUT2 */
}
static void serial_char(char ch) {
    for (K_U32 i = 0; i < 1000000u; ++i) {
        if ((port_in(COM1 + 5) & 0x20u) != 0) {
            port_out(COM1, (K_U8)ch);
            return;
        }
    }
}
static void serial_line(const char *text) {
    while (*text) serial_char(*text++);
    serial_char('\r');
    serial_char('\n');
}

__attribute__((noreturn)) static void stop(K_U8 code) {
    (void)code;
#ifdef KOSCHEI_QEMU_TEST
    /* Only present in test image; QEMU ISA debug-exit = (code << 1) | 1. */
    port_out(0xf4, code);
#endif
    for (;;) __asm__ __volatile__("cli; hlt");
}

#ifdef KOSCHEI_QEMU_PF_TEST
#include "cpu_pf_guest_probe.h"
#include "live_cpu_observation.h"
#include "live_image_residency.h"
#include "live_cr3_inspection.h"
#include "owned_tables_guest_probe.h"
#include "multi_pt_guest_probe.h"

/* Record actual CPU-supplied CR2/error in the UART receipt, not placeholders. */
static void k0_cpu_pf_serial_hex(K_U64 value) {
    const char *digits = "0123456789abcdef";
    for (int shift = 60; shift >= 0; shift -= 4)
        serial_char(digits[(value >> (K_U32)shift) & 15ULL]);
}
/* QEMU profile has 256 MiB RAM and OVMF identity mappings; never use
 * these pointer casts on a production EFI image or external hardware.
 * Do not dereference MMIO/runtime or unknown physical frame provenance.
 */
typedef struct {
    const void *map;
    K_U64 map_size, stride;
} K0_QEMU_TABLE_READER;

static int k0_qemu_read_active_pte(void *opaque, K_U64 table,
                                   K_U32 slot, K_U64 *value) {
    const K0_QEMU_TABLE_READER *reader =
        (const K0_QEMU_TABLE_READER *)opaque;
    if (!reader || !reader->map || !value || slot >= 512U ||
        !table || (table & (K0_PAGE_SIZE - 1)) ||
        table > (256ULL * 1024ULL * 1024ULL - K0_PAGE_SIZE) ||
        !k0_live_img_in_descriptor(reader->map, reader->map_size,
            reader->stride, table, K0_EFI_LOADER_DATA_TYPE,
            K0_EFI_BOOT_DATA_TYPE, K0_CONVENTIONAL_MEMORY) ||
        !k0_live_img_in_descriptor(reader->map, reader->map_size,
            reader->stride, table + K0_PAGE_SIZE - 1,
            K0_EFI_LOADER_DATA_TYPE, K0_EFI_BOOT_DATA_TYPE,
            K0_CONVENTIONAL_MEMORY))
        return 0;
    const volatile K_U64 *entries =
        (const volatile K_U64 *)(unsigned long long)table;
    *value = entries[slot]; /* current firmware identity mapping */
    return 1;
}

static void k0_live_cr3_serial_receipt(const K0_CR3_I_RESULT *rip,
                                       const K0_CR3_I_RESULT *rsp) {
    const char *prefix = "KOSCHEI-KERNEL K0 CR3-WALK/1 RIPPA=";
    const char *separator = " RSPPA=";
    const char *root = " CR3=";
    while (*prefix) serial_char(*prefix++);
    k0_cpu_pf_serial_hex(rip->physical_address);
    while (*separator) serial_char(*separator++);
    k0_cpu_pf_serial_hex(rsp->physical_address);
    while (*root) serial_char(*root++);
    k0_cpu_pf_serial_hex(rip->root_cr3);
    serial_line("");
}
static void k0_live_image_serial_receipt(K_U64 base, K_U64 size) {
    const char *prefix = "KOSCHEI-KERNEL K0 IMAGE-LIVE/1 BASE=";
    const char *separator = " SIZE=";
    while (*prefix) serial_char(*prefix++);
    k0_cpu_pf_serial_hex(base);
    while (*separator) serial_char(*separator++);
    k0_cpu_pf_serial_hex(size);
    serial_line("");
}
static void k0_cpu_live_field(const char *key, K_U64 value) {
    while (*key) serial_char(*key++);
    k0_cpu_pf_serial_hex(value);
}
static void k0_cpu_live_serial_receipt(const K0_LIVE_CPU_STATE *state) {
    const char *prefix = "KOSCHEI-KERNEL K0 CPU-LIVE/1";
    while (*prefix) serial_char(*prefix++);
    k0_cpu_live_field(" CR0=", state->cr0);
    k0_cpu_live_field(" CR3=", state->cr3);
    k0_cpu_live_field(" CR4=", state->cr4);
    k0_cpu_live_field(" EFER=", state->efer);
    k0_cpu_live_field(" RFLAGS=", state->rflags);
    k0_cpu_live_field(" CS=", state->cs);
    k0_cpu_live_field(" GDTR=", state->gdtr.base);
    k0_cpu_live_field(" GDTLIMIT=", state->gdtr.limit);
    k0_cpu_live_field(" IDTR=", state->idtr.base);
    k0_cpu_live_field(" IDTLIMIT=", state->idtr.limit);
    k0_cpu_live_field(" RIP=", state->rip);
    k0_cpu_live_field(" RSP=", state->rsp);
    serial_line("");
}
static void k0_cpu_pf_serial_receipt(void) {
    const char *prefix = "KOSCHEI-KERNEL K0 CPU-PF-TRAP/1 CR2=";
    const char *separator = " ERROR=";
    for (; *prefix; ++prefix) serial_char(*prefix);
    k0_cpu_pf_serial_hex(k0_cpu_probe_cr2);
    for (; *separator; ++separator) serial_char(*separator);
    k0_cpu_pf_serial_hex(k0_cpu_probe_error);
    serial_line("");
}
#endif

/*
 * QEMU K0.3 diagnostic only. The firmware-provided current address mapping
 * is used here: this is NOT an own-MMU or address-space isolation proof.
 * Two distinct claimed pages are written, read, zeroed and compared to
 * detect aliasing before returning them to the ledger. No firmware calls.
 */
static int k0_probe_claimed_pages(K0_PAGE_POOL *pool) {
    K_U64 first = 0, second = 0;
    if (!k0_pool_claim(pool, &first) || !k0_pool_claim(pool, &second) ||
        first == second || !k0_pool_is_claimed(pool, first) ||
        !k0_pool_is_claimed(pool, second)) return 0;
    volatile K_U8 *a = (volatile K_U8 *)(unsigned long long)first;
    volatile K_U8 *b = (volatile K_U8 *)(unsigned long long)second;
    for (K_U32 i = 0; i < K0_PAGE_SIZE; ++i) {
        a[i] = (K_U8)(i ^ 0xa5U);
        b[i] = (K_U8)((i * 3U) ^ 0x5aU);
    }
    for (K_U32 i = 0; i < K0_PAGE_SIZE; ++i)
        if (a[i] != (K_U8)(i ^ 0xa5U) ||
            b[i] != (K_U8)((i * 3U) ^ 0x5aU)) return 0;
    for (K_U32 i = 0; i < K0_PAGE_SIZE; ++i) a[i] = 0;
    for (K_U32 i = 0; i < K0_PAGE_SIZE; ++i)
        if (a[i] != 0 || b[i] != (K_U8)((i * 3U) ^ 0x5aU)) return 0;
    for (K_U32 i = 0; i < K0_PAGE_SIZE; ++i) b[i] = 0;
    for (K_U32 i = 0; i < K0_PAGE_SIZE; ++i)
        if (b[i] != 0) return 0;
    return k0_pool_release(pool, second) && k0_pool_release(pool, first) &&
           pool->active == 0;
}

/* x86_64-pc-windows-msvc target supplies required UEFI Microsoft x64 ABI. */
EFI_STATUS efi_main(EFI_HANDLE image, EFI_SYSTEM_TABLE *system) {
    (void)image;
    serial_init();
#ifdef KOSCHEI_QEMU_PF_TEST
    K_U64 loaded_image_base = 0, loaded_image_size = 0;
    K_U64 final_map_size = 0, final_map_stride = 0;
    K_U32 final_map_version = 0;
#endif
    if (!system || system->hdr.signature != 0x5453595320494249ULL ||
        !system->boot_services ||
        system->boot_services->hdr.signature != 0x56524553544f4f42ULL ||
        system->boot_services->hdr.header_size < 240 ||
        !system->boot_services->get_memory_map ||
        !system->boot_services->exit_boot_services) {
        serial_line("KOSCHEI-KERNEL REJECT/1 INVALID-UEFI");
        stop(0x11);
    }
    serial_line("KOSCHEI-KERNEL BOOT/1 X86_64-UEFI");
    serial_line("KOSCHEI-KERNEL K0 SERIAL-OWNED");
#ifdef KOSCHEI_QEMU_PF_TEST
    if (!k0_uefi_loaded_image_identity(image, system,
                                       &loaded_image_base, &loaded_image_size)) {
        serial_line("KOSCHEI-KERNEL REJECT/1 LOADED-IMAGE");
        stop(0x11);
    }
#endif
    /*
     * Firmware may change MapKey after GetMemoryMap. On stale-key rejection,
     * acquire a fresh map and retry at most three times. Never report exit
     * success before the firmware confirms it.
     */
    int exited = 0;
    K0_MEMORY_PLAN plan;
    for (K_U32 attempt = 0; attempt < 3; attempt++) {
        K_U64 map_size = sizeof(k0_map_buffer);
        K_U64 map_key = 0;
        K_U64 stride = 0;
        K_U32 version = 0;
        EFI_STATUS result = system->boot_services->get_memory_map(
            &map_size, k0_map_buffer, &map_key, &stride, &version);
        if (result != 0 || map_key == 0 ||
            !k0_memory_validate_plan(k0_map_buffer, map_size, stride, version, &plan) ||
            plan.candidate_pages != K0_PLAN_PAGES ||
            plan.candidate_start < 0x100000ULL) {
            serial_line("KOSCHEI-KERNEL REJECT/1 MEMORY-MAP");
            stop(0x11);
        }
        result = system->boot_services->exit_boot_services(image, map_key);
        if (result == 0) {
#ifdef KOSCHEI_QEMU_PF_TEST
            final_map_size = map_size;
            final_map_stride = stride;
            final_map_version = version;
#endif
            exited = 1;
            break;
        }
        /* EFI_INVALID_PARAMETER = EFIERR(2), typically stale MapKey. */
        if (result != (0x8000000000000000ULL | 2ULL)) break;
    }
    if (!exited) {
        serial_line("KOSCHEI-KERNEL REJECT/1 BOOT-SERVICES");
        stop(0x11);
    }
    /* No firmware boot-service calls after this point. */
    serial_line("KOSCHEI-KERNEL K0 MEMORY-MAP-VALIDATED");
    serial_line("KOSCHEI-KERNEL K0 FREE-PAGES-PLANNED");
    serial_line("KOSCHEI-KERNEL K0 BOOT-SERVICES-EXITED");
    if (!k0_pool_init(&k0_pool, &plan, exited) ||
        !k0_probe_claimed_pages(&k0_pool)) {
        serial_line("KOSCHEI-KERNEL REJECT/1 PAGE-POOL");
        stop(0x11);
    }
    serial_line("KOSCHEI-KERNEL K0 PAGE-POOL-PROBED");
    if (!k0_guest_roundtrip_table_frames(&k0_pool)) {
        serial_line("KOSCHEI-KERNEL REJECT/1 PAGE-TABLE-FRAMES");
        stop(0x11);
    }
    serial_line("KOSCHEI-KERNEL K0 PAGE-TABLE-FRAMES-ROUNDTRIP");
#ifdef KOSCHEI_QEMU_PF_TEST
    K0_LIVE_CPU_STATE cpu_live = {0};
    /* Diagnostic image only. Observe real CPU state before installing the
     * replacement #PF test IDT; never switch or rewrite CR3.
     */
    __asm__ __volatile__("cli" : : : "memory");
    if (!k0_live_snapshot_guest(&cpu_live) ||
        !k0_live_state_admissible(&cpu_live)) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CPU-LIVE");
        stop(0x11);
    }
    if (!k0_live_image_residency_preflight(
            k0_map_buffer, final_map_size, final_map_stride,
            final_map_version, loaded_image_base, loaded_image_size,
            cpu_live.rip, cpu_live.rsp, k0_pool.base) ||
        (K_U64)(unsigned long long)&efi_main < loaded_image_base ||
        (K_U64)(unsigned long long)&efi_main >=
            loaded_image_base + loaded_image_size ||
        (K_U64)(unsigned long long)&k0_cpu_pf_entry < loaded_image_base ||
        (K_U64)(unsigned long long)&k0_cpu_pf_entry >=
            loaded_image_base + loaded_image_size) {
        serial_line("KOSCHEI-KERNEL REJECT/1 IMAGE-RESIDENCY");
        stop(0x11);
    }
    /* Inspect existing CR3 table bytes, NEVER write CR3.
     * QEMU-only physical-table reads use the existing OVMF identity map.
     * Fail closed if frames are outside known 256MiB RAM / final UEFI
     * non-runtime data types. No CPU-translation attestation is claimed.
     */
    K0_QEMU_TABLE_READER reader = {
        k0_map_buffer, final_map_size, final_map_stride
    };
    K0_CR3_I_RESULT rip_walk = {0}, rsp_walk = {0};
    if (!k0_cr3_inspect_translation(cpu_live.cr3, cpu_live.rip,
                                    k0_qemu_read_active_pte,
                                    &reader, &rip_walk) ||
        !k0_cr3_inspect_translation(cpu_live.cr3, cpu_live.rsp - 1,
                                    k0_qemu_read_active_pte,
                                    &reader, &rsp_walk) ||
        rip_walk.physical_address != cpu_live.rip ||
        rsp_walk.physical_address != cpu_live.rsp - 1 ||
        rip_walk.effective_user || rsp_walk.effective_user ||
        rip_walk.effective_nx ||
        !k0_live_img_in_descriptor(k0_map_buffer, final_map_size,
            final_map_stride, rip_walk.physical_address,
            K0_EFI_LOADER_CODE_TYPE, K0_EFI_BOOT_CODE_TYPE,
            K0_EFI_LOADER_CODE_TYPE) ||
        !k0_live_img_in_descriptor(k0_map_buffer, final_map_size,
            final_map_stride, rsp_walk.physical_address,
            K0_EFI_LOADER_DATA_TYPE, K0_EFI_BOOT_DATA_TYPE,
            K0_CONVENTIONAL_MEMORY)) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CR3-WALK");
        stop(0x11);
    }
    /* Own six claimed frames ONLY AS DATA under existing firmware CR3.
     * Reconstruct all four table pages, verify actual physical bytes,
     * walk high-half W^X leaves, erase and release; never install CR3.
     */
    if (!k0_guest_owned_tables_physical_dryrun(&k0_pool, cpu_live.cr3)) {
        serial_line("KOSCHEI-KERNEL REJECT/1 OWNED-TABLES");
        stop(0x11);
    }
    /* QEMU only: three additional 2MiB-window PT pages written and
     * independently read as physical DATA; old firmware CR3 stays active.
     */
    if (!k0_mpt_guest_physical_dryrun(
            &k0_pool, cpu_live.cr3, k0_map_buffer, final_map_size,
            final_map_stride, final_map_version)) {
        serial_line("KOSCHEI-KERNEL REJECT/1 MULTI-PT");
        stop(0x11);
    }
    if (!k0_cpu_pf_real_guest_probe()) {
        serial_line("KOSCHEI-KERNEL REJECT/1 CPU-PF");
        stop(0x11);
    }
    k0_live_image_serial_receipt(loaded_image_base, loaded_image_size);
    k0_live_cr3_serial_receipt(&rip_walk, &rsp_walk);
    serial_line("KOSCHEI-KERNEL K0 OWNED-TABLES/1 PHYSICAL-READBACK CR3-UNCHANGED");
    serial_line("KOSCHEI-KERNEL K0 MULTI-PT/1 PHYSICAL-READBACK CR3-UNCHANGED");
    k0_cpu_live_serial_receipt(&cpu_live);
    k0_cpu_pf_serial_receipt();
#endif
    serial_line("KOSCHEI-KERNEL K0 HALT-NO-POLICY");
    stop(0x10);
}
