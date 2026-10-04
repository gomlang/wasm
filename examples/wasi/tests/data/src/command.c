/* Compiler integration fixture authored for gomlang/wasm (MIT).
 * Compile with wasi-sdk 24.0; this intentionally exercises real wasi-libc.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <wasi/api.h>

static int fail(const char *operation) {
    fprintf(stderr, "failure:%s errno=%d\n", operation, errno);
    return 99;
}

int main(int argc, char **argv) {
    if (argc > 1 && strcmp(argv[1], "exit") == 0) {
        fputs("requested-exit\n", stderr);
        return 23;
    }
    if (argc != 3) return fail("argc");
    const char *environment = getenv("GREETING");
    if (!environment) return fail("environment");
    printf("args=%d:%s:%s env=%s\n", argc, argv[1], argv[2], environment);

    char input[16] = {0};
    ssize_t count = read(STDIN_FILENO, input, sizeof(input) - 1);
    if (count < 0) return fail("stdin");
    printf("stdin=%s\n", input);

    int file = open("/sandbox/out.txt", O_CREAT | O_TRUNC | O_RDWR, 0644);
    if (file < 0) return fail("open");
    if (write(file, "payload", 7) != 7) return fail("write");
    if (lseek(file, 0, SEEK_SET) != 0) return fail("seek");
    char content[8] = {0};
    if (read(file, content, 7) != 7) return fail("read");
    struct stat metadata;
    if (fstat(file, &metadata) != 0) return fail("stat");
    if (close(file) != 0) return fail("close");
    printf("file=%s size=%lld\n", content, (long long)metadata.st_size);

    __wasi_timestamp_t now = 0;
    __wasi_errno_t status = __wasi_clock_time_get(__WASI_CLOCKID_MONOTONIC, 1, &now);
    if (status) { errno = status; return fail("clock"); }
    unsigned char entropy[4] = {0};
    status = __wasi_random_get(entropy, sizeof(entropy));
    if (status) { errno = status; return fail("random"); }
    printf("clock=%llu random=%02x%02x%02x%02x\n",
           (unsigned long long)now, entropy[0], entropy[1], entropy[2], entropy[3]);
    puts("done");
    return 0;
}
