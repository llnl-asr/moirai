#include <moirai/core/common/logging.h>
#include <moirai/core/moirai_main.h>

#include <moirai/moirai.hpp>

namespace moirai {
MoiraiCore::MoiraiCore()
    : conf_(Singleton<ConfigurationManager>::get_instance()),
      registry_(std::make_shared<EntityRegistry>()),
      is_initialized_(false),
      is_finalized_(false),
      is_active_(false) {
  MOIRAI_LOGGER_INIT();
  MOIRAI_LOG_TRACE();
}

bool MoiraiCore::initialize(const std::string& log_file) {
  MOIRAI_LOG_TRACE();
  std::lock_guard<std::mutex> lock(mtx_);
  if (is_initialized_) {
    MOIRAI_LOG_WARN("moirai is already initialized");
    return is_active_;
  }
  is_initialized_ = true;
  conf_->apply(ConfigurationSide::APP, log_file);
  // Activities are never aggregated: register their type before any is
  // logged.
  const DFTracerEventType activity = dftracer::event_type_of<ActivityType>();
  dftracer_register_event_type(&activity);
  initialize_main(nullptr, nullptr, nullptr);
  is_active_ = conf_->enable;
  MOIRAI_LOG_INFO("moirai initialized: enable %d trace_io %d log_file %s",
                  conf_->enable, conf_->trace_io, conf_->log_file.c_str());
  return is_active_;
}

void MoiraiCore::finalize() {
  MOIRAI_LOG_TRACE();
  std::lock_guard<std::mutex> lock(mtx_);
  if (!is_initialized_ || is_finalized_) return;
  is_finalized_ = true;
  is_active_ = false;
  ::finalize();
  MOIRAI_LOG_INFO("moirai finalized");
}

bool MoiraiCore::is_active() const {
  std::lock_guard<std::mutex> lock(mtx_);
  return is_active_;
}

std::shared_ptr<EntityRegistry> MoiraiCore::registry() const {
  std::lock_guard<std::mutex> lock(mtx_);
  return is_active_ ? registry_ : nullptr;
}
}  // namespace moirai
