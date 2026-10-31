#ifndef MOIRAI_CORE_ARTIFACT_ARTIFACT_STORE_H
#define MOIRAI_CORE_ARTIFACT_ARTIFACT_STORE_H
#include <moirai/core/common/datastructure.h>
#include <sys/types.h>

#include <memory>
#include <moirai/moirai.hpp>
#include <mutex>
#include <string>
#include <string_view>

namespace moirai {
/**
 * Large content next to a trace, so that provenance holds only its key.
 *
 * <log_file>.artifacts/<host>/ is a RocksDB of dftracer-utils, one per node as
 * the trace is, for all its producers. RocksDB has one open writer at a time,
 * so no producer keeps it open: a put waits in memory, and a batch takes the
 * database, writes and closes it, waiting for the producers before it. Content
 * is durable from that batch on: at ARTIFACT_FLUSH_BYTES and at finalize.
 *
 * A key is 16 hex digits, moirai's FNV-1a of the size and a constant-size
 * sample of the content (all of it, up to 64 KiB). Sampling lets different
 * content share a key, so a put that finds a key it stored compares: the same
 * content is a duplicate, other content takes the next key. Two processes can
 * only find that out when the second one's batch arrives, after it has handed
 * out the key: its content is then kept under <key>-<pid>, and a read of the
 * key gets the first.
 *
 * A transient artifact's content is in the database. A persistent one is a
 * link: the file's path, size and mtime, so a read can tell that the file has
 * since changed.
 */
class ArtifactStore {
 public:
  // writable false: the keys are computed, nothing is stored (tracing off, or
  // moirai built without dftracer-utils).
  ArtifactStore(std::string log_file, bool writable);
  ~ArtifactStore();

  Artifact put(std::string_view content);
  Artifact put_file(const std::string& path, Lifetime lifetime);
  bool read(const std::string& uri, std::string* content);

  static std::string root_of(const std::string& log_file);

 private:
  // A forked child starts with nothing of its parent's.
  void after_fork();
  void add(const std::string& key, std::string value);
  void flush();
  bool find(const std::string& key, std::string* value);

  std::mutex mtx_;
  std::string root_;
  bool writable_;
  pid_t pid_;
  ArtifactBatch batch_;
};
}  // namespace moirai
#endif  // MOIRAI_CORE_ARTIFACT_ARTIFACT_STORE_H
