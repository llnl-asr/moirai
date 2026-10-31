#ifndef MOIRAI_CORE_COMMON_ENUMERATION_H
#define MOIRAI_CORE_COMMON_ENUMERATION_H
#include <cstdint>

namespace moirai {
// Which side of dftracer a configuration is for.
enum class ConfigurationSide : uint8_t {
  APP = 0,     // the traced application
  SERVICE = 1  // dftracer_service, run by moirai-service
};

// The first byte of a value in the artifact store.
enum class ArtifactValue : char {
  CONTENT = 'C',  // the content follows
  LINK = 'L'      // size:mtime:path of a file
};
}  // namespace moirai
#endif  // MOIRAI_CORE_COMMON_ENUMERATION_H
