#include <moirai/core/common/logging.h>

#ifdef MOIRAI_DEBUG
#include <strings.h>

#include <cstdlib>

void moirai_logger_init() {
  const char* level = std::getenv("MOIRAI_LOG_LEVEL");
  int value = CPP_LOGGER_C_ERROR;
  if (level != nullptr) {
    if (strcasecmp(level, "TRACE") == 0)
      value = CPP_LOGGER_C_TRACE;
    else if (strcasecmp(level, "DEBUG") == 0)
      value = CPP_LOGGER_C_DEBUG;
    else if (strcasecmp(level, "INFO") == 0)
      value = CPP_LOGGER_C_INFO;
    else if (strcasecmp(level, "WARN") == 0)
      value = CPP_LOGGER_C_WARN;
  }
  cpp_logger_clog_level(value, MOIRAI_LOGGER_NAME);
}
#endif
