#include <grp.h>
#include <moirai/core/common/logging.h>
#include <moirai/core/moirai_main.h>
#include <pwd.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <moirai/moirai.hpp>
#include <string>

extern char** environ;

namespace moirai {
namespace {
// Configuration environment recorded as process metadata ("env.<NAME>"):
// moirai's and dftracer's own settings and threading, then the launcher's
// job, rank and size, and the devices the process may use.
const char* const kEnvPrefixes[] = {"MOIRAI_", "DFTRACER_", "OMP_"};
const char* const kEnvNames[] = {"FLUX_JOB_ID",
                                 "FLUX_JOB_SIZE",
                                 "FLUX_JOB_NNODES",
                                 "FLUX_TASK_RANK",
                                 "FLUX_TASK_LOCAL_ID",
                                 "FLUX_ENCLOSING_ID",
                                 "SLURM_JOB_ID",
                                 "SLURM_JOB_PARTITION",
                                 "SLURM_NNODES",
                                 "SLURM_NTASKS",
                                 "SLURM_PROCID",
                                 "SLURM_LOCALID",
                                 "SLURM_CPUS_PER_TASK",
                                 "PBS_JOBID",
                                 "LSB_JOBID",
                                 "COBALT_JOBID",
                                 "PMI_RANK",
                                 "PMI_SIZE",
                                 "PMIX_RANK",
                                 "PALS_RANKID",
                                 "MPI_LOCALRANKID",
                                 "OMPI_COMM_WORLD_RANK",
                                 "OMPI_COMM_WORLD_SIZE",
                                 "OMPI_COMM_WORLD_LOCAL_RANK",
                                 "MKL_NUM_THREADS",
                                 "OPENBLAS_NUM_THREADS",
                                 "CUDA_VISIBLE_DEVICES",
                                 "ROCR_VISIBLE_DEVICES",
                                 "HIP_VISIBLE_DEVICES",
                                 "NVIDIA_VISIBLE_DEVICES"};
// The job id: the first of these that is set.
const char* const kJobVars[] = {"FLUX_JOB_ID", "SLURM_JOB_ID", "PBS_JOBID",
                                "LSB_JOBID", "COBALT_JOBID"};
// Never recorded, whatever the prefix.
const char* const kSecret[] = {"TOKEN",   "SECRET", "PASSW", "CREDENTIAL",
                               "API_KEY", "APIKEY", "AUTH"};

bool wanted(const std::string& name) {
  for (const char* s : kSecret)
    if (name.find(s) != std::string::npos) return false;
  for (const char* p : kEnvPrefixes)
    if (name.rfind(p, 0) == 0) return true;
  for (const char* n : kEnvNames)
    if (name == n) return true;
  const char* extra = std::getenv("MOIRAI_METADATA_ENV");  // a,b,c: more names
  if (extra != nullptr) {
    std::string list = std::string(",") + extra + ",";
    if (list.find("," + name + ",") != std::string::npos) return true;
  }
  return false;
}

// Every occurrence of `name` in `text` replaced by `with`.
std::string mask(std::string text, const std::string& name,
                 const std::string& with) {
  if (name.size() < 3) return text;  // too short to mask without damage
  for (size_t at = text.find(name); at != std::string::npos;
       at = text.find(name, at + with.size()))
    text.replace(at, name.size(), with);
  return text;
}

std::string user_name() {
  if (const passwd* pw = getpwuid(getuid())) return pw->pw_name;
  const char* u = std::getenv("USER");
  return u != nullptr ? u : "";
}

std::string group_name() {
  if (const group* gr = getgrgid(getgid())) return gr->gr_name;
  return std::to_string(getgid());
}
}  // namespace

std::string MoiraiCore::identity_hash(const std::string& kind,
                                      const std::string& value) {
  const char* salt = std::getenv("MOIRAI_ID_SALT");
  const std::string salted = std::string(salt != nullptr ? salt : "") + value;
  char hex[MOIRAI_HEX_LEN];
  std::snprintf(hex, sizeof(hex), "%016llx",
                static_cast<unsigned long long>(
                    moirai_hash(kind.c_str(), salted.c_str())));
  return hex;
}

void MoiraiCore::write_metadata(const std::string& key,
                                const std::string& value) {
  char k[MOIRAI_URI_LEN], v[MOIRAI_URI_LEN];
  moirai_sanitize(k, sizeof(k), key.c_str());
  moirai_sanitize(v, sizeof(v), value.c_str());
  // A metadata region writes its key/value pair (a CM record) when it ends,
  // at the end of this scope.
  DFTracer record(k, v, DF_METADATA_EVENT);
}

void MoiraiCore::record_process() {
  MOIRAI_LOG_TRACE();
  const std::string user = user_name(), grp = group_name();
  const std::string uh = identity_hash("user", user);
  const std::string gh = identity_hash("group", grp);
  write_metadata("user_hash", uh);
  write_metadata("group_hash", gh);
  for (const char* var : kJobVars) {
    const char* job = std::getenv(var);
    if (job != nullptr && *job) {
      write_metadata("job", job);
      break;
    }
  }
  write_metadata("pid", std::to_string(getpid()));
  write_metadata("ppid", std::to_string(getppid()));
  write_metadata("moirai.enable", std::to_string(conf_->enable));
  write_metadata("moirai.trace_io", std::to_string(conf_->trace_io));
  // The names behind the hashes: identity entities related to nothing, so
  // dropping them anonymizes the trace without leaving a dangling id.
  registry_->declare_type("identity", MOIRAI_ROLE_REFERENCE,
                          "The name behind a hash (user, group): drop these "
                          "records to anonymize the trace.");
  if (!user.empty())
    registry_->declare("identity", uh, MOIRAI_STORE_MEMORY, uh + "=" + user);
  registry_->declare("identity", gh, MOIRAI_STORE_MEMORY, gh + "=" + grp);
  const char* off = std::getenv("MOIRAI_PROCESS_METADATA");
  if (off != nullptr && std::strcmp(off, "0") == 0) return;
  // The configuration environment, the user's name masked by its hash in
  // every value (paths under a home or a user's workspace).
  const std::string tag = "@user:" + uh;  // kept by moirai_sanitize
  for (char** e = environ; e != nullptr && *e != nullptr; ++e) {
    const char* eq = std::strchr(*e, '=');
    if (eq == nullptr) continue;
    const std::string name(*e, eq - *e);
    if (!wanted(name)) continue;
    write_metadata("env." + name, mask(eq + 1, user, tag));
  }
}
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
  artifacts_ = std::make_shared<ArtifactStore>(conf_->log_file, is_active_);
  if (is_active_) record_process();
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
  artifacts_.reset();
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

std::shared_ptr<ArtifactStore> MoiraiCore::artifacts() const {
  std::lock_guard<std::mutex> lock(mtx_);
  return artifacts_;
}
}  // namespace moirai
