/* ABI boundary fixture authored for gomlang/wasm (MIT).
 * Values outside linear memory are intentionally passed to host ABI functions.
 * The C code never dereferences those invalid pointers.
 */
#include <stddef.h>
#include <stdint.h>
#include <wasi/api.h>

#define EXPORT(name) __attribute__((export_name(name)))
#define BAD ((uintptr_t)0xfffffff0u)
static unsigned char buffer[32];
static const unsigned char secret[] = "SECRET";
static const char escape_path[] = "../outside";
static const char file_path[] = "data.txt";

EXPORT("buffer_pointer") uint32_t buffer_pointer(void) { return (uint32_t)(uintptr_t)buffer; }
EXPORT("args_sizes_bad") uint32_t args_sizes_bad(void) {
    return __wasi_args_sizes_get((__wasi_size_t *)BAD, (__wasi_size_t *)buffer);
}
EXPORT("args_get_bad") uint32_t args_get_bad(void) {
    return __wasi_args_get((uint8_t **)BAD, buffer);
}
EXPORT("environ_sizes_bad") uint32_t environ_sizes_bad(void) {
    return __wasi_environ_sizes_get((__wasi_size_t *)BAD, (__wasi_size_t *)buffer);
}
EXPORT("environ_get_bad") uint32_t environ_get_bad(void) {
    return __wasi_environ_get((uint8_t **)BAD, buffer);
}
EXPORT("write_bad_iov") uint32_t write_bad_iov(void) {
    __wasi_size_t count = 0;
    return __wasi_fd_write(1, (const __wasi_ciovec_t *)BAD, 1, &count);
}
EXPORT("write_bad_result") uint32_t write_bad_result(void) {
    __wasi_ciovec_t iov = {secret, sizeof(secret) - 1};
    return __wasi_fd_write(1, &iov, 1, (__wasi_size_t *)BAD);
}
EXPORT("write_second_iov_bad") uint32_t write_second_iov_bad(void) {
    __wasi_ciovec_t iov[2] = {{secret, sizeof(secret) - 1}, {(const uint8_t *)BAD, 1}};
    __wasi_size_t count = 0;
    return __wasi_fd_write(1, iov, 2, &count);
}
EXPORT("write_iov_misaligned") uint32_t write_iov_misaligned(void) {
    __wasi_size_t count = 0;
    return __wasi_fd_write(1, (const __wasi_ciovec_t *)(buffer + 1), 1, &count);
}
EXPORT("write_result_misaligned") uint32_t write_result_misaligned(void) {
    __wasi_ciovec_t iov = {secret, sizeof(secret) - 1};
    return __wasi_fd_write(1, &iov, 1, (__wasi_size_t *)(buffer + 1));
}
EXPORT("stat_misaligned") uint32_t stat_misaligned(void) {
    return __wasi_fd_filestat_get(1, (__wasi_filestat_t *)(buffer + 1));
}
EXPORT("clock_misaligned") uint32_t clock_misaligned(void) {
    return __wasi_clock_time_get(__WASI_CLOCKID_MONOTONIC, 1, (__wasi_timestamp_t *)(buffer + 1));
}
EXPORT("read_bad_result") uint32_t read_bad_result(void) {
    __wasi_iovec_t iov = {buffer, sizeof(buffer)};
    return __wasi_fd_read(0, &iov, 1, (__wasi_size_t *)BAD);
}
EXPORT("read_valid") uint32_t read_valid(void) {
    __wasi_iovec_t iov = {buffer, sizeof(buffer)};
    __wasi_size_t count = 0;
    __wasi_errno_t result = __wasi_fd_read(0, &iov, 1, &count);
    return result ? 0x80000000u | result : count;
}
EXPORT("write_stdin") uint32_t write_stdin(void) {
    __wasi_ciovec_t iov = {secret, sizeof(secret) - 1};
    __wasi_size_t count = 0;
    return __wasi_fd_write(0, &iov, 1, &count);
}
EXPORT("clock_bad_result") uint32_t clock_bad_result(void) {
    return __wasi_clock_time_get(__WASI_CLOCKID_MONOTONIC, 1, (__wasi_timestamp_t *)BAD);
}
EXPORT("clock_disabled") uint32_t clock_disabled(void) {
    return __wasi_clock_time_get(__WASI_CLOCKID_MONOTONIC, 1, (__wasi_timestamp_t *)buffer);
}
EXPORT("random_bad_buffer") uint32_t random_bad_buffer(void) {
    return __wasi_random_get((uint8_t *)BAD, 4);
}
EXPORT("random_disabled") uint32_t random_disabled(void) {
    return __wasi_random_get(buffer, 4);
}
EXPORT("open_missing_preopen") uint32_t open_missing_preopen(void) {
    __wasi_fd_t result;
    return __wasi_path_open(3, 0, file_path, 0, __WASI_RIGHTS_FD_READ, 0, 0, &result);
}
EXPORT("open_parent_escape") uint32_t open_parent_escape(void) {
    __wasi_fd_t result;
    return __wasi_path_open(3, 0, escape_path, 0, __WASI_RIGHTS_FD_READ, 0, 0, &result);
}
EXPORT("open_bad_result") uint32_t open_bad_result(void) {
    return __wasi_path_open(3, 0, file_path, __WASI_OFLAGS_CREAT, __WASI_RIGHTS_FD_READ | __WASI_RIGHTS_FD_WRITE, 0, 0, (__wasi_fd_t *)BAD);
}
EXPORT("open_readonly") uint32_t open_readonly(void) {
    __wasi_fd_t result = 0;
    __wasi_errno_t status = __wasi_path_open(3, 0, file_path, 0, __WASI_RIGHTS_FD_READ, 0, 0, &result);
    return status ? 0x80000000u | status : result;
}
EXPORT("write_descriptor") uint32_t write_descriptor(uint32_t fd) {
    __wasi_ciovec_t iov = {secret, sizeof(secret) - 1};
    __wasi_size_t count = 0;
    return __wasi_fd_write(fd, &iov, 1, &count);
}
EXPORT("exit_37") void exit_37(void) { __wasi_proc_exit(37); }
