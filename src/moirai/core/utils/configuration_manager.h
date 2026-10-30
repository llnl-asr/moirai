#ifndef MOIRAI_CORE_UTILS_CONFIGURATION_MANAGER_H
#define MOIRAI_CORE_UTILS_CONFIGURATION_MANAGER_H
#include <moirai/core/common/enumeration.h>

#include <string>
#include <utility>
#include <vector>

namespace moirai {
/**
 * moirai's run-time configuration, read from MOIRAI_* (include/moirai/
 * moirai.h), and its translation into dftracer's: every MOIRAI_<X> is
 * DFTRACER_<X>, except moirai's own settings below; producer/consumer mode
 * is always on, and dftracer is always started by moirai (FUNCTION: the
 * application calls moirai_initialize). dftracer reads its configuration
 * when it starts, so
 * apply() runs before dftracer is initialized (MoiraiCore, MoiraiService).
 */
class ConfigurationManager {
 public:
  bool enable;           // MOIRAI_ENABLE (default on)
  bool trace_io;         // MOIRAI_TRACE_IO (default: MOIRAI_TRACE_IO at build)
  std::string log_file;  // MOIRAI_LOG_FILE
  std::string dftracer_service;  // MOIRAI_DFTRACER_SERVICE

  ConfigurationManager();

  // Sets dftracer's environment for the given side. log_file, when not
  // empty, overrides MOIRAI_LOG_FILE.
  void apply(ConfigurationSide side, const std::string& log_file = "");

 private:
  // MOIRAI_<X> settings that are dftracer's DFTRACER_<X>.
  std::vector<std::pair<std::string, std::string>> passthrough_;

  static bool own_setting(const std::string& name);
  static bool flag(const char* value, bool otherwise);
};
}  // namespace moirai
#endif  // MOIRAI_CORE_UTILS_CONFIGURATION_MANAGER_H
