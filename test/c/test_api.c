/* The provenance scenario through moirai's C API; checked by
 * test/check_provenance.py. With the argument "direct", only entities and
 * entity relations, declared directly, without any activity. MOIRAI_TEST_DATA
 * is the directory of the file the "load" activity writes and reads. */
#include <fcntl.h>
#include <moirai/moirai.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void file_io(void) {
  const char* dir = getenv("MOIRAI_TEST_DATA");
  char path[4096], buf[64];
  int fd;
  if (dir == NULL) return;
  snprintf(path, sizeof(path), "%s/load.bin", dir);
  fd = open(path, O_CREAT | O_WRONLY | O_TRUNC, 0644);
  if (fd < 0) return;
  memset(buf, 'x', sizeof(buf));
  if (write(fd, buf, sizeof(buf)) < 0) perror("write");
  close(fd);
  fd = open(path, O_RDONLY);
  if (fd < 0) return;
  if (read(fd, buf, sizeof(buf)) < 0) perror("read");
  close(fd);
}

static void relations(MoiraiId in0, MoiraiId in1, MoiraiId cfg, MoiraiId m0,
                      MoiraiId m1) {
  moirai_relate(MOIRAI_REL_DERIVED_FROM, m0, in0);
  moirai_relate(MOIRAI_REL_REVISION_OF, m1, m0);
  moirai_relate(MOIRAI_REL_CONTAINS, cfg, in0);
  moirai_relate(MOIRAI_REL_PART_OF, in1, in0);
  moirai_relate(MOIRAI_REL_SPECIALIZATION_OF, m1, m0);
  moirai_relate(MOIRAI_REL_ALTERNATE_OF, in1, in0);
  moirai_relate(MOIRAI_REL_DEPENDS_ON, m0, cfg);
  /* An activity relation between entities, and no entity: ignored. */
  moirai_relate(MOIRAI_REL_USED, m0, in0);
  moirai_relate(MOIRAI_REL_DEPENDS_ON, MOIRAI_NONE, in0);
}

int main(int argc, char* argv[]) {
  const int direct = argc > 1 && strcmp(argv[1], "direct") == 0;
  MoiraiId in0, in1, cfg, m0, m1, tmp;
  moirai_initialize(NULL);

  moirai_entity_type("dataset", MOIRAI_ROLE_INPUT, "raw input");
  moirai_entity_type("model", MOIRAI_ROLE_OUTPUT, "trained model");
  moirai_entity_type("config", MOIRAI_ROLE_PARAMETER, "run settings");
  moirai_entity_type("dataset", MOIRAI_ROLE_OUTPUT, "declared again: ignored");

  in0 = moirai_entity("dataset", "in0", MOIRAI_STORE_PARALLEL_FS,
                      "file:///data/in0.h5");
  in1 = moirai_entity("dataset", "in1", MOIRAI_STORE_LOCAL_DISK, "/tmp/in1");
  cfg = moirai_entity("config", "run", MOIRAI_STORE_MEMORY, NULL);
  moirai_entity("dataset", "in0", MOIRAI_STORE_PARALLEL_FS, "again: ignored");

  if (direct) {
    m0 = moirai_entity("model", "m0", MOIRAI_STORE_PARALLEL_FS,
                       "file:///data/m0.pt");
    m1 = moirai_entity("model", "m1", MOIRAI_STORE_OBJECT_STORE,
                       "s3://bucket/m1");
    tmp = moirai_entity("dataset", "tmp", MOIRAI_STORE_MEMORY, NULL);
    (void)tmp;
    relations(in0, in1, cfg, m0, m1);
    moirai_finalize();
    return 0;
  }

  {
    MOIRAI_C_ACTIVITY_START(load);
    MOIRAI_C_ACTIVITY_USED(load, in0);
    MOIRAI_C_ACTIVITY_USED(load, in1);
    MOIRAI_C_ACTIVITY_RELATE(load, MOIRAI_REL_USED, cfg);
    file_io();
    MOIRAI_C_ACTIVITY_END(load);
  }
  {
    struct MoiraiActivityData* train = moirai_activity_begin("train");
    moirai_activity_relate(train, MOIRAI_REL_USED, in0);
    moirai_activity_relate(train, MOIRAI_REL_UPDATED, cfg);
    m0 = moirai_activity_relate_entity(train, MOIRAI_REL_GENERATED, "model",
                                       "m0", MOIRAI_STORE_PARALLEL_FS,
                                       "file:///data/m0.pt");
    moirai_activity_end(train);
  }
  {
    MOIRAI_C_ACTIVITY_START(refine);
    m1 = moirai_entity("model", "m1", MOIRAI_STORE_OBJECT_STORE,
                       "s3://bucket/m1");
    MOIRAI_C_ACTIVITY_USED(refine, m0);
    MOIRAI_C_ACTIVITY_GENERATED(refine, m1);
    MOIRAI_C_ACTIVITY_INVALIDATED(refine, m0);
    /* An entity relation on an activity: ignored. */
    MOIRAI_C_ACTIVITY_RELATE(refine, MOIRAI_REL_DERIVED_FROM, m1);
    /* Ended when the block is left (MOIRAI_C_ACTIVITY_CLEANUP). */
  }
  {
    MOIRAI_C_ACTIVITY_START(cleanup);
    tmp = moirai_activity_relate_entity(moirai_cleanup, MOIRAI_REL_USED,
                                        "dataset", "tmp", MOIRAI_STORE_MEMORY,
                                        NULL);
    MOIRAI_C_ACTIVITY_INVALIDATED(cleanup, tmp);
    MOIRAI_C_ACTIVITY_END(cleanup);
  }
  relations(in0, in1, cfg, m0, m1);

  moirai_finalize();
  return 0;
}
