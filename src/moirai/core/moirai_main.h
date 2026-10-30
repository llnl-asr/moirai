#ifndef MOIRAI_CORE_MOIRAI_MAIN_H
#define MOIRAI_CORE_MOIRAI_MAIN_H
#include <moirai/core/common/singleton.h>
#include <moirai/core/provenance/entity_registry.h>
#include <moirai/core/utils/configuration_manager.h>

#include <memory>
#include <mutex>
#include <string>

namespace moirai {
/**
 * moirai in this process: its configuration, dftracer underneath it, and the
 * entity registry. initialize() configures dftracer for provenance
 * (ConfigurationManager::apply), registers moirai's event types and starts
 * dftracer; finalize() stops it. One per process, through
 * MOIRAI_MAIN_SINGLETON(); every API, C, C++ and Python, goes through it.
 */
class MoiraiCore {
 public:
  MoiraiCore();

  // Returns whether tracing is on. Calling it again does nothing.
  bool initialize(const std::string& log_file = "");
  void finalize();
  bool is_active() const;

  std::shared_ptr<ConfigurationManager> configuration() const { return conf_; }
  // The registry, or nullptr when not tracing.
  std::shared_ptr<EntityRegistry> registry() const;

 private:
  mutable std::mutex mtx_;
  std::shared_ptr<ConfigurationManager> conf_;
  std::shared_ptr<EntityRegistry> registry_;
  bool is_initialized_;
  bool is_finalized_;
  bool is_active_;
};
}  // namespace moirai

#define MOIRAI_MAIN_SINGLETON() \
  moirai::Singleton<moirai::MoiraiCore>::get_instance()
#endif  // MOIRAI_CORE_MOIRAI_MAIN_H
