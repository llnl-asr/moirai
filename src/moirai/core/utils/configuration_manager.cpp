#include <moirai/core/common/constants.h>
#include <moirai/core/common/logging.h>
#include <moirai/core/utils/configuration_manager.h>
#include <moirai/moirai_config.h>
#include <strings.h>

#include <cstdlib>
#include <cstring>
#include <filesystem>

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
         name == "ENABLE_PC_MODE" ||
         name.rfind(MOIRAI_ENV_AGENT_PREFIX, 0) == 0;
}

std::string ConfigurationManager::expand_data_dir(const std::string& value) {
  namespace fs = std::filesystem;
  if (value.empty() || value == MOIRAI_DATA_DIR_ALL) return value;
  std::vector<std::string> entries;
  auto add = [&entries](const std::string& entry) {
    if (entry.empty()) return;
    for (const auto& e : entries)
      if (e == entry) return;
    entries.push_back(entry);
  };
  size_t begin = 0;
  while (begin <= value.size()) {
    size_t end = value.find(':', begin);
    if (end == std::string::npos) end = value.size();
    const std::string entry = value.substr(begin, end - begin);
    begin = end + 1;
    add(entry);
    if (entry.empty() || entry == MOIRAI_DATA_DIR_ALL) continue;
    std::error_code ec;
    const fs::path real = fs::canonical(entry, ec);
    if (ec) continue;  // not there: as given
    std::string given = entry;
    while (given.size() > 1 && given.back() == '/') given.pop_back();
    if (real.string() != given) add(real.string());
  }
  std::string out;
  for (const auto& e : entries) out += (out.empty() ? "" : ":") + e;
  return out;
}

void ConfigurationManager::configure_agent() {
  namespace fs = std::filesystem;
  const char* v = env(MOIRAI_ENV_AGENT_DIR);
  const char* home = env(MOIRAI_ENV_HOME);
  std::string dir = v != nullptr ? v : DEFAULT_AGENT_DIR;
  if (dir.rfind("~/", 0) == 0 && home != nullptr)
    dir = std::string(home) + dir.substr(1);
  std::error_code ec;
  const fs::path absolute = fs::absolute(dir, ec);
  agent_dir = (ec ? fs::path(dir) : absolute).lexically_normal().string();
  if ((v = env(MOIRAI_ENV_AGENT_REDACT)) != nullptr) agent_redact = v;
  if ((v = env(MOIRAI_ENV_AGENT_SENSITIVE_PATHS)) != nullptr)
    agent_sensitive_paths = v;
}

ConfigurationManager::ConfigurationManager()
    : enable(flag(env(MOIRAI_ENV_ENABLE), true)),
      trace_io(flag(env(MOIRAI_ENV_TRACE_IO), MOIRAI_DEFAULT_TRACE_IO != 0)) {
  // The first of moirai's actors to be made, by MoiraiCore or MoiraiService.
  MOIRAI_LOGGER_INIT();
  MOIRAI_LOG_TRACE();
  if (const char* v = env(MOIRAI_ENV_LOG_FILE)) log_file = v;
  if (const char* v = env(MOIRAI_ENV_DFTRACER_SERVICE)) dftracer_service = v;
  configure_agent();
  const size_t prefix = std::strlen(MOIRAI_ENV_PREFIX);
  for (char** e = environ; e != nullptr && *e != nullptr; ++e) {
    if (std::strncmp(*e, MOIRAI_ENV_PREFIX, prefix) != 0) continue;
    const char* eq = std::strchr(*e, '=');
    if (eq == nullptr) continue;
    settings.emplace_back(std::string(*e, static_cast<size_t>(eq - *e)),
                          eq + 1);
    std::string name(*e + prefix, static_cast<size_t>(eq - (*e + prefix)));
    if (!name.empty() && !own_setting(name))
      passthrough_.emplace_back("DFTRACER_" + name,
                                name == MOIRAI_ENV_DATA_DIR
                                    ? expand_data_dir(eq + 1)
                                    : std::string(eq + 1));
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
    set("DFTRACER_DATA_DIR", MOIRAI_DATA_DIR_ALL);
  // moirai starts dftracer itself, from moirai_initialize.
  set("DFTRACER_INIT", "FUNCTION");
}
}  // namespace moirai
