#ifndef MOIRAI_CORE_COMMON_LOGGING_H
#define MOIRAI_CORE_COMMON_LOGGING_H
/*
 * moirai's internal logging, as dftracer's: through cpp-logger in the _dbg
 * builds (MOIRAI_DEBUG; level from MOIRAI_LOG_LEVEL), compiled out of the
 * release builds.
 */
#define MOIRAI_NOOP_MACRO \
  do {                    \
  } while (0)

#ifdef MOIRAI_DEBUG
#if __has_include(<cpp-logger/clogger.h>)
#include <cpp-logger/clogger.h>
#else
// cpp-logger's C API, for a dftracer wheel that bundles libcpp-logger but
// not its headers.
#define CPP_LOGGER_C_PRINT 1
#define CPP_LOGGER_C_ERROR 2
#define CPP_LOGGER_C_WARN 3
#define CPP_LOGGER_C_INFO 4
#define CPP_LOGGER_C_DEBUG 5
#define CPP_LOGGER_C_TRACE 6
extern "C" {
void cpp_logger_clog(const int logger_level, const char* name,
                     const char* string, ...);
void cpp_logger_clog_level(const int logger_level, const char* name);
}
#endif
#include <dlfcn.h>

#include <chrono>
#include <cstdio>
#include <ctime>
#include <string>

#define MOIRAI_LOGGER_NAME "MOIRAI"

// moirai runs inside a process whose stdio dftracer intercepts, and cpp-logger
// writes with stdio: format with libc's own snprintf (not the intercepted
// one), and make a log from inside a log a no-op, so that logging can never
// recurse through the interception.
using moirai_logging_snprintf_fn = int (*)(char*, size_t, const char*, ...);
inline moirai_logging_snprintf_fn moirai_logging_real_snprintf() {
  static auto fn = reinterpret_cast<moirai_logging_snprintf_fn>(
      dlsym(RTLD_NEXT, "snprintf"));
  return fn != nullptr ? fn : &std::snprintf;
}

class MoiraiLogReentryGuard {
 public:
  MoiraiLogReentryGuard() : entered_(!active()) {
    if (entered_) active() = true;
  }
  ~MoiraiLogReentryGuard() {
    if (entered_) active() = false;
  }
  bool should_log() const { return entered_; }

 private:
  static bool& active() {
    static thread_local bool in_logging = false;
    return in_logging;
  }
  bool entered_;
};

inline std::string moirai_log_time() {
  using namespace std::chrono;
  const auto now = system_clock::now();
  const auto ms =
      duration_cast<milliseconds>(now.time_since_epoch()).count() % 1000;
  const std::time_t t = system_clock::to_time_t(now);
  std::tm tm{};
  localtime_r(&t, &tm);
  char out[64];
  moirai_logging_real_snprintf()(
      out, sizeof(out), "%04d-%02d-%02d %02d:%02d:%02d.%03ld",
      tm.tm_year + 1900, tm.tm_mon + 1, tm.tm_mday, tm.tm_hour, tm.tm_min,
      tm.tm_sec, static_cast<long>(ms));
  return out;
}

template <typename... Args>
inline void moirai_log(const char* file, int line, const char* function,
                       int level, const char* format, Args... args) {
  MoiraiLogReentryGuard guard;
  if (!guard.should_log()) return;
  char message[4096];
  moirai_logging_real_snprintf()(message, sizeof(message), format, args...);
  cpp_logger_clog(level, MOIRAI_LOGGER_NAME, "[%s] %s %s [%s:%d]",
                  moirai_log_time().c_str(), function, message, file, line);
}

// TRACE: the start of a function, and its end when the scope is left.
class MoiraiTraceScope {
 public:
  MoiraiTraceScope(const char* file, int line, const char* function)
      : file_(file), line_(line), function_(function) {
    moirai_log(file_, line_, function_, CPP_LOGGER_C_TRACE, "start");
  }
  ~MoiraiTraceScope() {
    moirai_log(file_, line_, function_, CPP_LOGGER_C_TRACE, "end");
  }
  MoiraiTraceScope(const MoiraiTraceScope&) = delete;
  MoiraiTraceScope& operator=(const MoiraiTraceScope&) = delete;

 private:
  const char* file_;
  int line_;
  const char* function_;
};

// Sets the level from MOIRAI_LOG_LEVEL (ERROR, WARN, INFO, DEBUG, TRACE).
void moirai_logger_init();

// Levels, as dftracer's:
//   TRACE  start and end of a function (MOIRAI_LOG_TRACE() at its top)
//   DEBUG  values, for debugging
//   INFO   information on what moirai does
//   WARN   warnings (misuse moirai ignores)
//   ERROR  errors
#define MOIRAI_LOGGER_INIT() moirai_logger_init()
#define MOIRAI_LOG(level, ...) \
  moirai_log(__FILE__, __LINE__, __FUNCTION__, level, __VA_ARGS__)
#define MOIRAI_LOG_TRACE() \
  MoiraiTraceScope moirai_trace_scope_(__FILE__, __LINE__, __FUNCTION__)
#define MOIRAI_LOG_DEBUG(...) MOIRAI_LOG(CPP_LOGGER_C_DEBUG, __VA_ARGS__)
#define MOIRAI_LOG_INFO(...) MOIRAI_LOG(CPP_LOGGER_C_INFO, __VA_ARGS__)
#define MOIRAI_LOG_WARN(...) MOIRAI_LOG(CPP_LOGGER_C_WARN, __VA_ARGS__)
#define MOIRAI_LOG_ERROR(...) MOIRAI_LOG(CPP_LOGGER_C_ERROR, __VA_ARGS__)
#else
#define MOIRAI_LOGGER_INIT() MOIRAI_NOOP_MACRO
#define MOIRAI_LOG_TRACE() MOIRAI_NOOP_MACRO
#define MOIRAI_LOG_DEBUG(...) MOIRAI_NOOP_MACRO
#define MOIRAI_LOG_INFO(...) MOIRAI_NOOP_MACRO
#define MOIRAI_LOG_WARN(...) MOIRAI_NOOP_MACRO
#define MOIRAI_LOG_ERROR(...) MOIRAI_NOOP_MACRO
#endif
#endif  // MOIRAI_CORE_COMMON_LOGGING_H
