#import <Foundation/Foundation.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char *argv[]) {
    (void)argc;
    @autoreleasepool {
        NSURL *script = [[NSBundle.mainBundle resourceURL] URLByAppendingPathComponent:@"Rustmatics/Rustmatics.sh"];
        const char *path = script.fileSystemRepresentation;
        if (path == NULL) {
            fprintf(stderr, "Rustmatics could not locate its bundled launcher.\n");
            return EXIT_FAILURE;
        }

        // Python modules live in the sealed application bundle.
        if (setenv("PYTHONDONTWRITEBYTECODE", "1", 1) != 0) {
            perror("Rustmatics could not configure Python");
            return EXIT_FAILURE;
        }

        argv[0] = (char *)path;
        execv(path, argv);
        perror("Rustmatics could not start its bundled launcher");
        return EXIT_FAILURE;
    }
}
