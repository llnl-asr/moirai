#ifndef MOIRAI_CORE_COMMON_DATASTRUCTURE_H
#define MOIRAI_CORE_COMMON_DATASTRUCTURE_H
#include <moirai/core/common/constants.h>
#include <moirai/core/common/enumeration.h>

#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_map>
#include <unordered_set>

namespace moirai {
// FNV-1a over any number of pieces.
class Fnv {
  uint64_t h_ = FNV_OFFSET;

 public:
  void update(const void* data, size_t size) {
    auto p = static_cast<const unsigned char*>(data);
    for (size_t i = 0; i < size; ++i) {
      h_ ^= p[i];
      h_ *= FNV_PRIME;
    }
  }
  uint64_t value() const { return h_ == 0 ? 1 : h_; }
};

// What a process holds for the node's artifact database between batches.
struct ArtifactBatch {
  std::unordered_map<std::string, std::string> values;  // key -> value
  std::unordered_set<std::string> known;  // keys this process has stored
  size_t bytes = 0;

  void clear_values() {
    values.clear();
    bytes = 0;
  }
};
}  // namespace moirai
#endif  // MOIRAI_CORE_COMMON_DATASTRUCTURE_H
