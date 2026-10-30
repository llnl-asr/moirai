/* moirai's artifact store through its C adapter; MOIRAI_TEST_DATA is the
 * directory of the linked file. */
#include <moirai/moirai.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define EXPECT(cond)                        \
  if (!(cond)) {                            \
    fprintf(stderr, "failed: %s\n", #cond); \
    return 1;                               \
  }

int main(void) {
  char uri[MOIRAI_ARTIFACT_URI_LEN], link[MOIRAI_ARTIFACT_URI_LEN];
  char path[1024];
  void* back = NULL;
  size_t size = 0;
  FILE* f;
  const char* content = "abc";
  char expected[MOIRAI_ARTIFACT_URI_LEN];

  snprintf(path, sizeof(path), "%s/kept.txt", getenv("MOIRAI_TEST_DATA"));
  f = fopen(path, "w");
  EXPECT(f != NULL);
  fputs(content, f);
  fclose(f);

  moirai_initialize(NULL);
  EXPECT(moirai_artifact(content, 3, uri));
  strcpy(expected, uri);
  EXPECT(strlen(uri) == MOIRAI_ARTIFACT_URI_LEN - 1);
  EXPECT(moirai_artifact_read(uri, &back, &size, NULL));
  EXPECT(size == 3 && memcmp(back, content, 3) == 0);
  free(back);
  EXPECT(moirai_entity("tool.output", "c", MOIRAI_STORE_DATABASE, uri) !=
         MOIRAI_NONE);

  EXPECT(moirai_artifact_file(path, MOIRAI_ARTIFACT_PERSISTENT, link));
  EXPECT(strcmp(link, expected) == 0);
  EXPECT(!moirai_artifact_file("/nonexistent", MOIRAI_ARTIFACT_TRANSIENT, uri));
  EXPECT(
      !moirai_artifact_read(MOIRAI_ARTIFACT_SCHEME "00", &back, &size, NULL));
  moirai_finalize();
  return 0;
}
