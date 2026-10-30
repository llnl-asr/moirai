// The provenance scenario through moirai's C++ actors; checked by
// test/check_provenance.py. "cleanup" runs on another thread. With the
// argument "direct", only entities and entity relations, without any
// activity. MOIRAI_TEST_DATA is the directory of the file "load" writes and
// reads.
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <moirai/moirai.hpp>
#include <string>
#include <thread>

static void file_io() {
  const char* dir = std::getenv("MOIRAI_TEST_DATA");
  if (dir == nullptr) return;
  const std::string path = std::string(dir) + "/load.bin";
  {
    std::ofstream(path) << std::string(64, 'x');
  }
  std::string back;
  std::ifstream(path) >> back;
}

static void relations(const moirai::Entity& in0, const moirai::Entity& in1,
                      const moirai::Entity& cfg, const moirai::Entity& m0,
                      const moirai::Entity& m1) {
  m0.relate(MOIRAI_REL_DERIVED_FROM, in0);
  m1.relate(MOIRAI_REL_REVISION_OF, m0);
  cfg.relate(MOIRAI_REL_CONTAINS, in0);
  in1.relate(MOIRAI_REL_PART_OF, in0);
  m1.relate(MOIRAI_REL_SPECIALIZATION_OF, m0);
  in1.relate(MOIRAI_REL_ALTERNATE_OF, in0);
  m0.relate(MOIRAI_REL_DEPENDS_ON, cfg);
  m0.relate(MOIRAI_REL_USED, in0);  // not an entity relation
  moirai::Entity(MOIRAI_NONE).relate(MOIRAI_REL_DEPENDS_ON, in0);
}

int main(int argc, char* argv[]) {
  const bool direct = argc > 1 && std::strcmp(argv[1], "direct") == 0;
  moirai::initialize();

  moirai::EntityType dataset("dataset", MOIRAI_ROLE_INPUT, "raw input");
  moirai::EntityType model("model", MOIRAI_ROLE_OUTPUT, "trained model");
  moirai::EntityType config("config", MOIRAI_ROLE_PARAMETER, "run settings");
  moirai::EntityType again("dataset", MOIRAI_ROLE_OUTPUT, "again: ignored");

  const moirai::Entity in0("dataset", "in0", MOIRAI_STORE_PARALLEL_FS,
                           "file:///data/in0.h5");
  const moirai::Entity in1("dataset", "in1", MOIRAI_STORE_LOCAL_DISK,
                           "/tmp/in1");
  const moirai::Entity cfg("config", "run");
  moirai::Entity("dataset", "in0", MOIRAI_STORE_PARALLEL_FS, "again: ignored");

  if (direct) {
    const moirai::Entity m0("model", "m0", MOIRAI_STORE_PARALLEL_FS,
                            "file:///data/m0.pt");
    const moirai::Entity m1("model", "m1", MOIRAI_STORE_OBJECT_STORE,
                            "s3://bucket/m1");
    moirai::Entity("dataset", "tmp");
    relations(in0, in1, cfg, m0, m1);
    moirai::finalize();
    return 0;
  }

  {
    MOIRAI_CPP_ACTIVITY(load);
    moirai_load.used(in0);
    moirai_load.used(in1);
    moirai_load.used(cfg);
    file_io();
  }
  moirai::Entity m0(MOIRAI_NONE);
  {
    moirai::Activity train("train");
    train.used(in0);
    train.updated(cfg);
    m0 = train.generates("model", "m0", MOIRAI_STORE_PARALLEL_FS,
                         "file:///data/m0.pt");
  }
  moirai::Entity m1(MOIRAI_NONE);
  {
    moirai::Activity refine("refine");
    m1 = moirai::Entity("model", "m1", MOIRAI_STORE_OBJECT_STORE,
                        "s3://bucket/m1");
    refine.used(m0);
    refine.generated(m1);
    refine.invalidated(m0);
    refine.relate(MOIRAI_REL_DERIVED_FROM, m1);  // not an activity relation
  }
  std::thread([] {
    moirai::Activity cleanup("cleanup");
    const moirai::Entity tmp = cleanup.uses("dataset", "tmp");
    cleanup.invalidated(tmp);
  }).join();
  relations(in0, in1, cfg, m0, m1);

  moirai::finalize();
  return 0;
}
