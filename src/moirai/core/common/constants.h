#ifndef MOIRAI_CORE_COMMON_CONSTANTS_H
#define MOIRAI_CORE_COMMON_CONSTANTS_H
#include <cstddef>
#include <cstdint>

// moirai's settings. ConfigurationManager reads them, once; everything else
// asks it.
#define MOIRAI_ENV_PREFIX "MOIRAI_"
#define MOIRAI_ENV_ENABLE "MOIRAI_ENABLE"
#define MOIRAI_ENV_TRACE_IO "MOIRAI_TRACE_IO"
#define MOIRAI_ENV_LOG_FILE "MOIRAI_LOG_FILE"
#define MOIRAI_ENV_LOG_LEVEL "MOIRAI_LOG_LEVEL"
#define MOIRAI_ENV_DFTRACER_SERVICE "MOIRAI_DFTRACER_SERVICE"
#define MOIRAI_ENV_AGENT_DIR "MOIRAI_AGENT_DIR"
#define MOIRAI_ENV_AGENT_REDACT "MOIRAI_AGENT_REDACT"
#define MOIRAI_ENV_AGENT_SENSITIVE_PATHS "MOIRAI_AGENT_SENSITIVE_PATHS"
// dftracer's DATA_DIR, the name after MOIRAI_ or DFTRACER_, and its
// "everything".
#define MOIRAI_ENV_DATA_DIR "DATA_DIR"
#define MOIRAI_DATA_DIR_ALL "all"
#define MOIRAI_ENV_HOME "HOME"
// Prefix of the settings moirai.agent owns: not dftracer's.
#define MOIRAI_ENV_AGENT_PREFIX "AGENT_"

namespace moirai {
constexpr const char* DEFAULT_AGENT_DIR = "~/.moirai/agent";
constexpr const char* DEFAULT_LOG_PREFIX = "moirai";
constexpr const char* ARTIFACTS_SUFFIX = ".artifacts";

// FNV-1a, as moirai_hash.
constexpr uint64_t FNV_OFFSET = 1469598103934665603ULL;
constexpr uint64_t FNV_PRIME = 1099511628211ULL;

// An artifact's key is of its size and content; past SAMPLE_FULL, of
// SAMPLE_COUNT blocks spread from its first byte to its last.
constexpr uint64_t SAMPLE_FULL = 64 << 10;
constexpr uint64_t SAMPLE_BLOCK = 1 << 10;
constexpr uint64_t SAMPLE_COUNT = 64;

constexpr size_t READ_BLOCK = 1 << 20;
// Puts wait in memory for this many bytes, then go to the node's database.
constexpr size_t ARTIFACT_FLUSH_BYTES = 8 << 20;
// How long a batch waits for the producers before it on the node, in ms.
constexpr int ARTIFACT_WAIT_MS = 120000;
constexpr int ARTIFACT_WAIT_STEP_MS = 5;
// Large values go to blob files, away from the LSM tree.
constexpr uint64_t ARTIFACT_MIN_BLOB = 4096;
}  // namespace moirai
#endif  // MOIRAI_CORE_COMMON_CONSTANTS_H
