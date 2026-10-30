#include <moirai/core/artifact/artifact_store.h>
#include <moirai/core/common/logging.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <exception>
#include <filesystem>
#include <fstream>
#include <thread>
#include <vector>

#if MOIRAI_HAS_ARTIFACT_STORE
#include <dftracer/utils/index/store/database.h>
#endif

namespace moirai {
namespace {
// The bytes hashed for size bytes of content; read(offset, n, out) gets them.
template <typename Read>
uint64_t sampled_key(uint64_t size, Read read) {
  Fnv fnv;
  fnv.update(&size, sizeof(size));
  char block[SAMPLE_BLOCK];
  if (size <= SAMPLE_FULL) {
    for (uint64_t at = 0; at < size; at += SAMPLE_BLOCK) {
      const uint64_t n = std::min(SAMPLE_BLOCK, size - at);
      read(at, n, block);
      fnv.update(block, n);
    }
    return fnv.value();
  }
  for (uint64_t i = 0; i < SAMPLE_COUNT; ++i) {
    read(i * (size - SAMPLE_BLOCK) / (SAMPLE_COUNT - 1), SAMPLE_BLOCK, block);
    fnv.update(block, SAMPLE_BLOCK);
  }
  return fnv.value();
}

uint64_t key_of(std::string_view content) {
  return sampled_key(content.size(), [&](uint64_t at, uint64_t n, char* out) {
    std::memcpy(out, content.data() + at, n);
  });
}

std::string hex_of(uint64_t key) {
  char hex[MOIRAI_HEX_LEN];
  moirai_hex(key, hex);
  return hex;
}

bool key_of_file(const std::string& path, uint64_t* key, uint64_t* size) {
  std::error_code ec;
  *size = std::filesystem::file_size(path, ec);
  if (ec) return false;
  std::ifstream in(path, std::ios::binary);
  if (!in) return false;
  *key = sampled_key(*size, [&](uint64_t at, uint64_t n, char* out) {
    in.seekg(static_cast<std::streamoff>(at));
    in.read(out, static_cast<std::streamsize>(n));
  });
  return !in.fail();
}

Artifact artifact_of(uint64_t key, uint64_t size, Lifetime lifetime) {
  return Artifact{MOIRAI_ARTIFACT_SCHEME + hex_of(key), size, lifetime};
}

}  // namespace

#if MOIRAI_HAS_ARTIFACT_STORE
namespace {
using Database = dftracer::utils::index::store::RocksDatabase;

bool read_file(const std::string& path, std::string* content) {
  std::ifstream in(path, std::ios::binary);
  if (!in) return false;
  std::vector<char> block(READ_BLOCK);
  while (in) {
    in.read(block.data(), static_cast<std::streamsize>(block.size()));
    content->append(block.data(), static_cast<size_t>(in.gcount()));
  }
  return !in.bad();
}

long long mtime_of(const std::string& path) {
  struct stat st{};
  if (::stat(path.c_str(), &st) != 0) return 0;
  return st.st_mtim.tv_sec * 1000000000LL + st.st_mtim.tv_nsec;
}

// A different content under a key: the next key, still 16 hex digits.
uint64_t next_key(uint64_t key, uint64_t attempt) {
  Fnv fnv;
  fnv.update(&key, sizeof(key));
  fnv.update(&attempt, sizeof(attempt));
  return fnv.value();
}

std::string link_value(const std::string& path, uint64_t size) {
  return std::string(1, static_cast<char>(ArtifactValue::LINK)) +
         std::to_string(size) + ":" + std::to_string(mtime_of(path)) + ":" +
         std::filesystem::absolute(path).lexically_normal().string();
}

// A value's content: its own, or that of the file it links to if that is
// still the file: same key, and past SAMPLE_FULL, where the key is of samples
// and an edit between them would not show, the same mtime too.
bool value_content(const std::string& value, const std::string& hex,
                   std::string* content) {
  if (value.empty()) return false;
  if (value[0] == static_cast<char>(ArtifactValue::CONTENT)) {
    content->assign(value, 1, std::string::npos);
    return true;
  }
  if (value[0] != static_cast<char>(ArtifactValue::LINK)) return false;
  const size_t a = value.find(':'), b = value.find(':', a + 1);
  if (a == std::string::npos || b == std::string::npos) return false;
  const uint64_t size = std::stoull(value.substr(1, a - 1));
  const std::string path = value.substr(b + 1);
  std::string bytes;
  if (!read_file(path, &bytes) || bytes.size() != size ||
      hex_of(key_of(bytes)) != hex)
    return false;
  if (size > SAMPLE_FULL &&
      std::to_string(mtime_of(path)) != value.substr(a + 1, b - a - 1))
    return false;
  *content = std::move(bytes);
  return true;
}

// Whether a stored value is this content. Only a key already taken gets here,
// so the comparison sampling saved is paid only by real duplicates.
bool same_content(const std::string& value, const std::string& hex,
                  std::string_view content) {
  std::string stored;
  return value_content(value, hex, &stored) && stored == content;
}

void configure(Database& db) {
  db.set_cf_options_override(
      [](const std::string&, ::rocksdb::ColumnFamilyOptions& options) {
        options.enable_blob_files = true;
        options.min_blob_size = ARTIFACT_MIN_BLOB;
        options.blob_compression_type = ::rocksdb::kZSTD;
        options.compression = ::rocksdb::kZSTD;
      });
}

// RocksDB's thread pools are global and threads do not survive fork: in a
// child the pools count threads that are gone, so a close waits forever for
// background work nobody runs. Growing them past the stale count starts real
// ones. (A fork while a pool's lock is held is not covered: fork with RocksDB
// idle, as with any library's threads.)
void restart_thread_pools(::rocksdb::Env* env) {
  static pid_t pool_pid = -1;
  const pid_t pid = ::getpid();
  if (pool_pid == pid) return;
  const bool forked = pool_pid != -1;
  pool_pid = pid;
  if (!forked) return;
  for (auto priority :
       {::rocksdb::Env::Priority::BOTTOM, ::rocksdb::Env::Priority::LOW,
        ::rocksdb::Env::Priority::HIGH})
    env->SetBackgroundThreads(env->GetBackgroundThreads(priority) + 8,
                              priority);
}

// RocksDatabase::open throws as well as it returns false, and a held lock is
// nothing exceptional here: it is another producer's turn.
bool try_open(Database& db, const std::string& path,
              Database::OpenMode mode = Database::OpenMode::ReadWrite) {
  try {
    return db.open(path, mode);
  } catch (const std::exception&) {
    return false;
  }
}

std::string hostname() {
  char host[256] = "host";
  ::gethostname(host, sizeof(host) - 1);
  return host;
}
}  // namespace

void ArtifactStore::after_fork() {
  const pid_t pid = ::getpid();
  if (pid == pid_) return;
  pid_ = pid;
  batch_.clear_values();
}

void ArtifactStore::add(const std::string& key, std::string value) {
  batch_.bytes += value.size();
  batch_.known.insert(key);
  batch_.values[key] = std::move(value);
  if (batch_.bytes >= ARTIFACT_FLUSH_BYTES) flush();
}

void ArtifactStore::flush() {
  if (batch_.values.empty()) return;
  ::mkdir(root_.c_str(), 0700);
  // The node's producers take turns; if this one never gets its turn, it must
  // not lose what it holds.
  std::string path = root_ + "/" + hostname();
  Database db;
  configure(db);
  bool opened = false;
  for (int waited = 0;
       !(opened = try_open(db, path)) && waited < ARTIFACT_WAIT_MS;
       waited += ARTIFACT_WAIT_STEP_MS)
    std::this_thread::sleep_for(
        std::chrono::milliseconds(ARTIFACT_WAIT_STEP_MS));
  if (!opened) {
    path += "-" + std::to_string(pid_);
    if (!try_open(db, path)) {
      MOIRAI_LOG_WARN("artifact store: cannot open %s", path.c_str());
      return;
    }
  }
  restart_thread_pools(db.get()->GetEnv());
  // One key at a time: each stands alone, and RocksDB's WriteBatch is not among
  // the symbols dftracer-utils exports.
  for (const auto& entry : batch_.values) {
    std::string stored, key = entry.first;
    if (db.get(key, &stored).ok()) {
      std::string content;
      if (stored == entry.second ||
          (value_content(entry.second, key, &content) &&
           same_content(stored, key, content)))
        continue;
      MOIRAI_LOG_WARN("artifact %s: another process has other content",
                      key.c_str());
      key += "-" + std::to_string(pid_);
    }
    if (!db.put(key, entry.second).ok())
      MOIRAI_LOG_WARN("artifact %s: put failed", key.c_str());
  }
  db.close();
  batch_.clear_values();
}

bool ArtifactStore::find(const std::string& key, std::string* value) {
  auto held = batch_.values.find(key);
  if (held != batch_.values.end()) {
    *value = held->second;
    return true;
  }
  std::error_code ec;
  for (const auto& entry : std::filesystem::directory_iterator(root_, ec)) {
    if (!entry.is_directory(ec)) continue;
    // Read-only takes no lock: a writer may be at work.
    Database db;
    configure(db);
    if (try_open(db, entry.path().string(), Database::OpenMode::ReadOnly) &&
        db.get(key, value).ok())
      return true;
  }
  return false;
}

ArtifactStore::~ArtifactStore() {
  std::lock_guard<std::mutex> lock(mtx_);
  if (::getpid() == pid_) flush();
}

Artifact ArtifactStore::put(std::string_view content) {
  uint64_t key = key_of(content);
  if (!writable_)
    return artifact_of(key, content.size(), MOIRAI_ARTIFACT_TRANSIENT);
  std::lock_guard<std::mutex> lock(mtx_);
  after_fork();
  // Stored once: the same content is the same key. A key taken by other
  // content, which sampling allows, moves on rather than lose either.
  for (uint64_t attempt = 1; batch_.known.count(hex_of(key)) != 0; ++attempt) {
    const std::string hex = hex_of(key);
    std::string value;
    if (find(hex, &value) && same_content(value, hex, content))
      return artifact_of(key, content.size(), MOIRAI_ARTIFACT_TRANSIENT);
    key = next_key(key, attempt);
  }
  std::string value(1, static_cast<char>(ArtifactValue::CONTENT));
  value.append(content);
  add(hex_of(key), std::move(value));
  return artifact_of(key, content.size(), MOIRAI_ARTIFACT_TRANSIENT);
}

Artifact ArtifactStore::put_file(const std::string& path, Lifetime lifetime) {
  if (lifetime == MOIRAI_ARTIFACT_TRANSIENT) {
    std::string bytes;
    if (!read_file(path, &bytes)) {
      MOIRAI_LOG_WARN("artifact: cannot read %s", path.c_str());
      return Artifact{};
    }
    return put(bytes);
  }
  uint64_t key = 0, size = 0;
  if (!key_of_file(path, &key, &size)) {
    MOIRAI_LOG_WARN("artifact: cannot read %s", path.c_str());
    return Artifact{};
  }
  if (writable_) {
    std::lock_guard<std::mutex> lock(mtx_);
    after_fork();
    // The newest link wins: the file is what a reader will need to find.
    add(hex_of(key), link_value(path, size));
  }
  return artifact_of(key, size, MOIRAI_ARTIFACT_PERSISTENT);
}

bool ArtifactStore::read(const std::string& uri, std::string* content) {
  const std::string scheme = MOIRAI_ARTIFACT_SCHEME;
  if (uri.compare(0, scheme.size(), scheme) != 0) return false;
  const std::string key = uri.substr(scheme.size());
  std::lock_guard<std::mutex> lock(mtx_);
  after_fork();
  std::string value;
  return find(key, &value) && value_content(value, key, content);
}
#else
void ArtifactStore::after_fork() {}
void ArtifactStore::add(const std::string&, std::string) {}
void ArtifactStore::flush() {}
bool ArtifactStore::find(const std::string&, std::string*) { return false; }
ArtifactStore::~ArtifactStore() = default;

Artifact ArtifactStore::put(std::string_view content) {
  return artifact_of(key_of(content), content.size(),
                     MOIRAI_ARTIFACT_TRANSIENT);
}

Artifact ArtifactStore::put_file(const std::string& path, Lifetime lifetime) {
  uint64_t key = 0, size = 0;
  if (!key_of_file(path, &key, &size)) return Artifact{};
  return artifact_of(key, size, lifetime);
}

bool ArtifactStore::read(const std::string&, std::string*) { return false; }
#endif

ArtifactStore::ArtifactStore(std::string log_file, bool writable)
    : root_(root_of(log_file)), writable_(writable), pid_(::getpid()) {}

std::string artifact_uri(std::string_view content) {
  return MOIRAI_ARTIFACT_SCHEME + hex_of(key_of(content));
}

std::string ArtifactStore::root_of(const std::string& log_file) {
  return (log_file.empty() ? std::string(DEFAULT_LOG_PREFIX) : log_file) +
         ARTIFACTS_SUFFIX;
}
}  // namespace moirai
