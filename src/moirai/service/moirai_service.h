#ifndef MOIRAI_SERVICE_MOIRAI_SERVICE_H
#define MOIRAI_SERVICE_MOIRAI_SERVICE_H
#include <moirai/core/utils/configuration_manager.h>

#include <memory>
#include <string>

namespace moirai {
/**
 * dftracer_service run for moirai: configured for provenance the same way
 * MoiraiCore configures the application (ConfigurationManager::apply, the
 * SERVICE side), then started or stopped. The service binary is
 * MOIRAI_DFTRACER_SERVICE, else the dftracer wheel's next to moirai's (in the
 * wheel), else the one moirai was built with.
 */
class MoiraiService {
 public:
  explicit MoiraiService(std::shared_ptr<ConfigurationManager> conf);

  // Runs `dftracer_service <command>` in place of this process; returns
  // only if it could not be run.
  int run(const std::string& command);
  const std::string& binary() const { return binary_; }

 private:
  std::shared_ptr<ConfigurationManager> conf_;
  std::string binary_;
};
}  // namespace moirai
#endif  // MOIRAI_SERVICE_MOIRAI_SERVICE_H
