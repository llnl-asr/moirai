#include <moirai/core/common/logging.h>
#include <moirai/core/utils/configuration_manager.h>
#include <moirai/moirai_config.h>
#include <strings.h>

#include <cstdlib>
#include <cstring>

extern char** environ;

namespace moirai {
namespace {
const char* env(const char* name) {
  const char* value = std::getenv(name);
  return value != nullptr && *value != '\0' ? value : nullptr;
}
void set(const std::string& name, const std::string& value) {
  MOIRAI_LOG_DEBUG("%s=%s", name.c_str(), value.c_str());
  setenv(name.c_str(), value.c_str(), 1);
}
}  // namespace

bool ConfigurationManager::flag(const char* value, bool otherwise) {
  if (value == nullptr) return otherwise;
  return !(std::strcmp(value, "0") == 0 || strcasecmp(value, "false") == 0 ||
           strcasecmp(value, "off") == 0 || strcasecmp(value, "no") == 0);
}

bool ConfigurationManager::own_setting(const std::string& name) {
  return name == "ENABLE" || name == "INIT" || name == "TRACE_IO" ||
         name == "LOG_FILE" || name == "DFTRACER_SERVICE" ||
         name == "ENABLE_PC_MODE";
}

ConfigurationManager::ConfigurationManager()
    : enable(flag(env("MOIRAI_ENABLE"), true)),
      trace_io(flag(env("MOIRAI_TRACE_IO"), MOIRAI_DEFAULT_TRACE_IO != 0)) {
  // The first of moirai's actors to be made, by MoiraiCore or MoiraiService.
  MOIRAI_LOGGER_INIT();
  MOIRAI_LOG_TRACE();
  if (const char* v = env("MOIRAI_LOG_FILE")) log_file = v;
  if (const char* v = env("MOIRAI_DFTRACER_SERVICE")) dftracer_service = v;
  for (char** e = environ; e != nullptr && *e != nullptr; ++e) {
    if (std::strncmp(*e, "MOIRAI_", 7) != 0) continue;
    const char* eq = std::strchr(*e, '=');
    if (eq == nullptr) continue;
    std::string name(*e + 7, static_cast<size_t>(eq - (*e + 7)));
    if (!name.empty() && !own_setting(name))
      passthrough_.emplace_back("DFTRACER_" + name, eq + 1);
  }
  MOIRAI_LOG_INFO(
      "configuration: enable %d trace_io %d log_file %s, %zu dftracer "
      "settings passed through",
      enable, trace_io, log_file.c_str(), passthrough_.size());
}

void ConfigurationManager::apply(ConfigurationSide side,
                                 const std::string& log_file_override) {
  MOIRAI_LOG_TRACE();
  MOIRAI_LOG_INFO("configuring dftracer for the %s",
                  side == ConfigurationSide::APP ? "application" : "service");
  for (const auto& setting : passthrough_) set(setting.first, setting.second);
  set("DFTRACER_ENABLE", enable ? "1" : "0");
  // Provenance always goes through the service (or its spill file).
  set("DFTRACER_ENABLE_PC_MODE", "1");
  if (!log_file_override.empty()) log_file = log_file_override;
  if (!log_file.empty()) set("DFTRACER_LOG_FILE", log_file);
  if (side == ConfigurationSide::SERVICE) {
    // The service is never itself traced.
    unsetenv("DFTRACER_INIT");
    return;
  }
  set("DFTRACER_DISABLE_IO", trace_io ? "0" : "1");
  if (std::getenv("DFTRACER_DATA_DIR") == nullptr)
    set("DFTRACER_DATA_DIR", "all");
  // moirai starts dftracer itself, from moirai_initialize.
  set("DFTRACER_INIT", "FUNCTION");
}
}  // namespace moirai
