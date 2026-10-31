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
  std::string artifact_shard;    // MOIRAI_ARTIFACT_SHARD (default: per process)
  // moirai.agent's, resolved.
  std::string agent_dir;     // MOIRAI_AGENT_DIR (default ~/.moirai/agent)
  std::string agent_redact;  // MOIRAI_AGENT_REDACT (default none)
  // MOIRAI_AGENT_SENSITIVE_PATHS (default none): globs added to moirai.agent's
  // built-in list of files whose names are not shown; passed through as is.
  std::string agent_sensitive_paths;

  // Every MOIRAI_<X> set, as it was: for a process that will not inherit it.
  std::vector<std::pair<std::string, std::string>> settings;

  ConfigurationManager();

  // MOIRAI_DATA_DIR as dftracer's DATA_DIR: the ':'-separated directories, each
  // followed by its real path when that differs (dftracer matches a path as the
  // program wrote it, and a project reached through a symbolic link is opened
  // by either). No entry twice, order kept; "all" and "" as they are, and an
  // entry that does not exist as given.
  static std::string expand_data_dir(const std::string& value);

  // The MOIRAI_<X> that are dftracer's, as DFTRACER_<X>: for a process that
  // will not be configured by moirai.
  const std::vector<std::pair<std::string, std::string>>& dftracer_settings()
      const {
    return passthrough_;
  }

  // Sets dftracer's environment for the given side. log_file, when not
  // empty, overrides MOIRAI_LOG_FILE.
  void apply(ConfigurationSide side, const std::string& log_file = "");

 private:
  // MOIRAI_<X> settings that are dftracer's DFTRACER_<X>.
  std::vector<std::pair<std::string, std::string>> passthrough_;

  static bool own_setting(const std::string& name);
  void configure_agent();
  static bool flag(const char* value, bool otherwise);
};
}  // namespace moirai
#endif  // MOIRAI_CORE_UTILS_CONFIGURATION_MANAGER_H
