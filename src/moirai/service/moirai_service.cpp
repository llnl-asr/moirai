#include <moirai/core/common/logging.h>
#include <moirai/service/moirai_service.h>
#include <unistd.h>

#include <cerrno>
#include <climits>
#include <cstring>

namespace moirai {
#ifdef MOIRAI_DFTRACER_SERVICE_RELATIVE
namespace {
// The directory of this executable.
std::string own_dir() {
  char path[PATH_MAX];
  const ssize_t n = readlink("/proc/self/exe", path, sizeof(path) - 1);
  if (n <= 0) return "";
  path[n] = '\0';
  std::string dir(path);
  const auto slash = dir.rfind('/');
  return slash == std::string::npos ? "" : dir.substr(0, slash);
}
}  // namespace
#endif

MoiraiService::MoiraiService(std::shared_ptr<ConfigurationManager> conf)
    : conf_(std::move(conf)) {
  MOIRAI_LOG_TRACE();
  if (!conf_->dftracer_service.empty()) {
    binary_ = conf_->dftracer_service;
  } else {
#ifdef MOIRAI_DFTRACER_SERVICE_RELATIVE
    // The wheel: the dftracer wheel's service, next to moirai's package.
    const std::string relative =
        own_dir() + "/" + MOIRAI_DFTRACER_SERVICE_RELATIVE;
    if (access(relative.c_str(), X_OK) == 0) binary_ = relative;
#endif
    if (binary_.empty()) binary_ = MOIRAI_DFTRACER_SERVICE_PATH;
  }
  MOIRAI_LOG_DEBUG("dftracer_service is %s", binary_.c_str());
}

int MoiraiService::run(const std::string& command) {
  MOIRAI_LOG_TRACE();
  conf_->apply(ConfigurationSide::SERVICE);
  MOIRAI_LOG_INFO("moirai-service: %s %s", binary_.c_str(), command.c_str());
  char* args[] = {const_cast<char*>(binary_.c_str()),
                  const_cast<char*>(command.c_str()), nullptr};
  execv(binary_.c_str(), args);
  MOIRAI_LOG_ERROR("moirai-service: cannot run %s: %s", binary_.c_str(),
                   std::strerror(errno));
  return 1;
}
}  // namespace moirai
