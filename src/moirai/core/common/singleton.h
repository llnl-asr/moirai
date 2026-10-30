#ifndef MOIRAI_CORE_COMMON_SINGLETON_H
#define MOIRAI_CORE_COMMON_SINGLETON_H

#include <memory>
#include <utility>

namespace moirai {
/**
 * One process-wide instance of T: Singleton<T>::get_instance(args...)
 * creates it on first use with args, then returns it; after finalize() it
 * returns nullptr. The same pattern as dftracer's Singleton.
 */
template <typename T>
class Singleton {
 public:
  template <typename... Args>
  static std::shared_ptr<T> get_instance(Args... args) {
    if (stop_flag()) return nullptr;
    auto& instance = instance_ref();
    if (instance == nullptr)
      instance = std::make_shared<T>(std::forward<Args>(args)...);
    return instance;
  }

  static void finalize() { stop_flag() = true; }

  Singleton(const Singleton&) = delete;
  Singleton& operator=(const Singleton&) = delete;

 private:
  // Kept alive until exit, so shared libraries never see it destroyed.
  static std::shared_ptr<T>& instance_ref() {
    static auto* instance = new std::shared_ptr<T>();
    return *instance;
  }
  static bool& stop_flag() {
    static auto* stop = new bool(false);
    return *stop;
  }

 protected:
  Singleton() {}
};
}  // namespace moirai
#endif  // MOIRAI_CORE_COMMON_SINGLETON_H
