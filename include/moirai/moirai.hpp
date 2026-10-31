// moirai's C++ API; moirai.h is its C connector (see it for the run-time
// configuration). Every class is an actor of the provenance record:
//
//   moirai::initialize();
//   moirai::EntityType dataset("dataset", MOIRAI_ROLE_INPUT, "raw input");
//   moirai::Entity in0("dataset", "in0", MOIRAI_STORE_PARALLEL_FS, uri);
//   {
//     moirai::Activity train("train");
//     train.used(in0);
//     moirai::Entity m0 = train.generates("model", "m0");
//     m0.relate(MOIRAI_REL_DERIVED_FROM, in0);
//   }
//   moirai::finalize();
#ifndef MOIRAI_MOIRAI_HPP
#define MOIRAI_MOIRAI_HPP
#include <dftracer/dftracer.h>
#include <moirai/moirai.h>

#include <cstdint>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace moirai {
using Id = MoiraiId;
using Store = MoiraiStore;
using Role = MoiraiRole;
using Relation = MoiraiRelation;
using Lifetime = MoiraiArtifactLifetime;

// moirai's dftracer event types, on its own layer.
// Activities: data events that are never aggregated -- every one is traced.
struct ActivityType : dftracer::EventType {
  static constexpr const char* category = MOIRAI_CATEGORY;
  static constexpr TraceEventType layer =
      static_cast<TraceEventType>(MOIRAI_LAYER);
  static constexpr bool aggregatable = false;
};
// Entities, entity types and entity relations: metadata records.
struct RecordType : dftracer::EventType {
  static constexpr const char* category = MOIRAI_CATEGORY;
  static constexpr TraceEventType layer = ActivityType::layer;
  static constexpr int kind = DF_METADATA_EVENT;
};
static_assert(MOIRAI_LAYER == DFTRACER_TRACE_TYPE_EXTERNAL,
              "moirai's layer is the first external dftracer layer");

// Configure dftracer for provenance and start tracing; returns whether
// tracing is on. log_file overrides MOIRAI_LOG_FILE when not empty.
bool initialize(const std::string& log_file = "");
void finalize();
bool is_active();

// An entity type, described once per process (an ET record).
class EntityType {
  std::string name_;

 public:
  EntityType(const std::string& name, Role role,
             const std::string& description = "");
  const std::string& name() const { return name_; }
};

// An entity: (type, key) and its id, declared once per process (an EH
// record). The key is hashed, never stored.
class Entity {
  Id id_;

 public:
  Entity(const std::string& type, const std::string& key,
         Store store = MOIRAI_STORE_MEMORY, const std::string& uri = "");
  // An entity already declared, by id.
  explicit Entity(Id id) : id_(id) {}
  Id id() const { return id_; }
  operator Id() const { return id_; }

  // Relate this entity, as subject, to another (an ER record); relation is
  // an entity relation, others are ignored.
  void relate(Relation relation, const Entity& object) const;
};

// An activity: one event, never aggregated, for the object's lifetime,
// relating it to the entities it used, generated, invalidated or updated.
// name must outlive the activity.
class Activity {
  DFTracer event_;

 public:
  explicit Activity(const char* name);
  ~Activity();
  Activity(const Activity&) = delete;
  Activity& operator=(const Activity&) = delete;

  // relation is an activity relation; others are ignored.
  void relate(Relation relation, const Entity& entity);
  // Declare (type, key) and relate it.
  Entity relate(Relation relation, const std::string& type,
                const std::string& key, Store store = MOIRAI_STORE_MEMORY,
                const std::string& uri = "");

  // What it really spanned, in microseconds since the epoch, when that is not
  // the object's lifetime: what ran in other processes, known afterwards. In
  // the event's args start_us and end_us; its own ts is when it was recorded.
  void span(uint64_t start_us, uint64_t end_us);

  void used(const Entity& entity) { relate(MOIRAI_REL_USED, entity); }
  void generated(const Entity& entity) { relate(MOIRAI_REL_GENERATED, entity); }
  void invalidated(const Entity& entity) {
    relate(MOIRAI_REL_INVALIDATED, entity);
  }
  void updated(const Entity& entity) { relate(MOIRAI_REL_UPDATED, entity); }
  Entity uses(const std::string& type, const std::string& key,
              Store store = MOIRAI_STORE_MEMORY, const std::string& uri = "") {
    return relate(MOIRAI_REL_USED, type, key, store, uri);
  }
  Entity generates(const std::string& type, const std::string& key,
                   Store store = MOIRAI_STORE_MEMORY,
                   const std::string& uri = "") {
    return relate(MOIRAI_REL_GENERATED, type, key, store, uri);
  }
};

// Content kept next to the trace, in <log file>.artifacts; give its uri to an
// Entity, so the trace holds only the key:
//
//   moirai::Artifact out = moirai::store_artifact(stdout_text);
//   moirai::Entity("tool.output", id, MOIRAI_STORE_DATABASE, out.uri);
struct Artifact {
  std::string uri;  // empty when the content could not be read
  uint64_t size = 0;
  Lifetime lifetime = MOIRAI_ARTIFACT_TRANSIENT;
  explicit operator bool() const { return !uri.empty(); }
};
// Store content (transient), once. Tracing off, it is only addressed.
Artifact store_artifact(std::string_view content);
// The uri content would have, storing nothing.
std::string artifact_uri(std::string_view content);
// A file: its content stored if transient, a link to it if persistent.
Artifact store_artifact_file(const std::string& path,
                             Lifetime lifetime = MOIRAI_ARTIFACT_PERSISTENT);
// The content at uri, from any process's shard; false if it is not there or a
// linked file has changed. log_file: the run's trace prefix; empty, this one.
bool read_artifact(const std::string& uri, std::string* content,
                   const std::string& log_file = "");

// moirai.agent's settings, from MOIRAI_AGENT_* (docs/agents.rst).
struct AgentConfiguration {
  std::string dir;
  std::string redact;
  std::string log_file;  // MOIRAI_LOG_FILE, or <dir>/trace
  // Every MOIRAI_<X> set, for a process that will not inherit it.
  std::vector<std::pair<std::string, std::string>> settings;
  // MOIRAI_AGENT_SENSITIVE_PATHS: globs added to the built-in sensitive files.
  std::string sensitive_paths;
  // The MOIRAI_<X> that are dftracer's, translated: DFTRACER_<X>.
  std::vector<std::pair<std::string, std::string>> dftracer_settings;
};
AgentConfiguration agent_configuration();
}  // namespace moirai

// Activities for the enclosing scope, as dftracer's regions:
// MOIRAI_CPP_FUNCTION() is moirai_fn, MOIRAI_CPP_ACTIVITY(name) is
// moirai_<name>.
#define MOIRAI_CPP_FUNCTION() moirai::Activity moirai_fn(__func__)
#define MOIRAI_CPP_ACTIVITY(name) moirai::Activity moirai_##name(#name)
#endif  // MOIRAI_MOIRAI_HPP
