// moirai's public API -- the C++ actors and their C connector -- on
// MoiraiCore (moirai_main.h).
#include <moirai/core/common/logging.h>
#include <moirai/core/moirai_main.h>

#include <moirai/moirai.hpp>

namespace moirai {
namespace {
// The registry while tracing, else nullptr.
std::shared_ptr<EntityRegistry> active_registry() {
  auto core = MOIRAI_MAIN_SINGLETON();
  return core != nullptr ? core->registry() : nullptr;
}
}  // namespace

bool initialize(const std::string& log_file) {
  MOIRAI_LOG_TRACE();
  auto core = MOIRAI_MAIN_SINGLETON();
  return core != nullptr && core->initialize(log_file);
}

void finalize() {
  MOIRAI_LOG_TRACE();
  auto core = MOIRAI_MAIN_SINGLETON();
  if (core == nullptr) return;
  core->finalize();
  Singleton<MoiraiCore>::finalize();
}

bool is_active() {
  auto core = MOIRAI_MAIN_SINGLETON();
  return core != nullptr && core->is_active();
}

EntityType::EntityType(const std::string& name, Role role,
                       const std::string& description)
    : name_(name) {
  MOIRAI_LOG_TRACE();
  MOIRAI_LOG_DEBUG("EntityType %s role %d", name.c_str(),
                   static_cast<int>(role));
  if (auto registry = active_registry())
    registry->declare_type(name, role, description);
}

Entity::Entity(const std::string& type, const std::string& key, Store store,
               const std::string& uri)
    : id_(EntityRegistry::id_of(type, key)) {
  MOIRAI_LOG_TRACE();
  MOIRAI_LOG_DEBUG("Entity %s/%s id %016llx store %d", type.c_str(),
                   key.c_str(), static_cast<unsigned long long>(id_),
                   static_cast<int>(store));
  if (auto registry = active_registry())
    registry->declare(type, key, store, uri);
}

void Entity::relate(Relation relation, const Entity& object) const {
  MOIRAI_LOG_TRACE();
  MOIRAI_LOG_DEBUG("Entity.relate %016llx %s %016llx",
                   static_cast<unsigned long long>(id_),
                   moirai_relation_name(relation),
                   static_cast<unsigned long long>(object.id()));
  auto registry = active_registry();
  if (registry != nullptr && !registry->relate(relation, id_, object.id()))
    MOIRAI_LOG_WARN(
        "Entity.relate ignored: %d is not an entity relation or an entity "
        "is missing",
        static_cast<int>(relation));
}

Activity::Activity(const char* name) : event_(name, ActivityType{}) {
  MOIRAI_LOG_TRACE();
  MOIRAI_LOG_DEBUG("Activity %s begins", name);
}

Activity::~Activity() { MOIRAI_LOG_TRACE(); }

void Activity::relate(Relation relation, const Entity& entity) {
  MOIRAI_LOG_TRACE();
  if (!moirai_relation_is_activity(relation) || entity.id() == MOIRAI_NONE) {
    MOIRAI_LOG_WARN(
        "Activity.relate ignored: %d is not an activity relation or the "
        "entity is missing",
        static_cast<int>(relation));
    return;
  }
  MOIRAI_LOG_DEBUG("Activity.relate %s %016llx", moirai_relation_name(relation),
                   static_cast<unsigned long long>(entity.id()));
  // The relation name is a static string; the id is kept by value.
  event_.append_id(MOIRAI_RELATIONS_ARG, moirai_relation_name(relation),
                   entity.id());
}

Entity Activity::relate(Relation relation, const std::string& type,
                        const std::string& key, Store store,
                        const std::string& uri) {
  MOIRAI_LOG_TRACE();
  Entity entity(type, key, store, uri);
  relate(relation, entity);
  return entity;
}
}  // namespace moirai

namespace {
std::string str(const char* s) { return s == nullptr ? std::string() : s; }
moirai::Activity* activity_of(struct MoiraiActivityData* data) {
  return data == nullptr ? nullptr
                         : static_cast<moirai::Activity*>(data->activity);
}
}  // namespace

extern "C" {
int moirai_initialize(const char* log_file) {
  MOIRAI_LOG_TRACE();
  return moirai::initialize(str(log_file)) ? 1 : 0;
}

void moirai_finalize(void) {
  MOIRAI_LOG_TRACE();
  moirai::finalize();
}

int moirai_is_active(void) { return moirai::is_active() ? 1 : 0; }

void moirai_entity_type(const char* type, MoiraiRole role,
                        const char* description) {
  MOIRAI_LOG_TRACE();
  if (type == nullptr) {
    MOIRAI_LOG_WARN("moirai_entity_type ignored: no type");
    return;
  }
  moirai::EntityType(type, role, str(description));
}

MoiraiId moirai_entity(const char* type, const char* key, MoiraiStore store,
                       const char* uri) {
  MOIRAI_LOG_TRACE();
  if (type == nullptr || key == nullptr) {
    MOIRAI_LOG_WARN("moirai_entity ignored: no type or key");
    return MOIRAI_NONE;
  }
  return moirai::Entity(type, key, store, str(uri)).id();
}

void moirai_relate(MoiraiRelation relation, MoiraiId subject, MoiraiId object) {
  MOIRAI_LOG_TRACE();
  moirai::Entity(subject).relate(relation, moirai::Entity(object));
}

struct MoiraiActivityData* moirai_activity_begin(const char* name) {
  MOIRAI_LOG_TRACE();
  if (name == nullptr) {
    MOIRAI_LOG_WARN("moirai_activity_begin ignored: no name");
    return nullptr;
  }
  auto data = new MoiraiActivityData();
  data->activity = new moirai::Activity(name);
  return data;
}

void moirai_activity_relate(struct MoiraiActivityData* data,
                            MoiraiRelation relation, MoiraiId entity) {
  MOIRAI_LOG_TRACE();
  if (auto activity = activity_of(data))
    activity->relate(relation, moirai::Entity(entity));
}

MoiraiId moirai_activity_relate_entity(struct MoiraiActivityData* data,
                                       MoiraiRelation relation,
                                       const char* type, const char* key,
                                       MoiraiStore store, const char* uri) {
  MOIRAI_LOG_TRACE();
  if (type == nullptr || key == nullptr) {
    MOIRAI_LOG_WARN("moirai_activity_relate_entity ignored: no type or key");
    return MOIRAI_NONE;
  }
  auto activity = activity_of(data);
  if (activity == nullptr)
    return moirai::Entity(type, key, store, str(uri)).id();
  return activity->relate(relation, type, key, store, str(uri)).id();
}

void moirai_activity_end(struct MoiraiActivityData* data) {
  MOIRAI_LOG_TRACE();
  if (data == nullptr) return;
  delete activity_of(data);
  delete data;
}

void moirai_activity_cleanup(struct MoiraiActivityData** data) {
  if (data == nullptr) return;
  moirai_activity_end(*data);
  *data = nullptr;
}
}
