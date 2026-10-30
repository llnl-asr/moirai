#include <moirai/core/common/logging.h>
#include <moirai/core/provenance/entity_registry.h>

#include <moirai/moirai.hpp>

namespace moirai {
MoiraiId EntityRegistry::id_of(const std::string& type,
                               const std::string& key) {
  char t[MOIRAI_TYPE_LEN];
  moirai_sanitize(t, sizeof(t), type.c_str());
  return moirai_hash(t, key.c_str());
}

bool EntityRegistry::first_time(std::unordered_set<MoiraiId>& seen,
                                MoiraiId id) {
  std::lock_guard<std::mutex> lock(mtx_);
  return seen.insert(id).second;
}

bool EntityRegistry::declare_type(const std::string& type, MoiraiRole role,
                                  const std::string& description) {
  MOIRAI_LOG_TRACE();
  char t[MOIRAI_TYPE_LEN], d[MOIRAI_DESC_LEN];
  moirai_sanitize(t, sizeof(t), type.c_str());
  if (!first_time(types_, moirai_hash(t, ""))) {
    MOIRAI_LOG_DEBUG("entity type %s already recorded", t);
    return false;
  }
  MOIRAI_LOG_DEBUG("ET type %s role %d", t, static_cast<int>(role));
  moirai_sanitize(d, sizeof(d), description.c_str());
  // Fields are kept by pointer until the record is written, at the end of
  // this scope.
  DFTracer record(MOIRAI_RECORD_ENTITY_TYPE, RecordType{});
  record.update("type", t);
  record.update("role", static_cast<int>(role));
  record.update("description", d);
  return true;
}

MoiraiId EntityRegistry::declare(const std::string& type,
                                 const std::string& key, MoiraiStore store,
                                 const std::string& uri) {
  MOIRAI_LOG_TRACE();
  char t[MOIRAI_TYPE_LEN];
  moirai_sanitize(t, sizeof(t), type.c_str());
  const MoiraiId id = moirai_hash(t, key.c_str());
  if (!first_time(entities_, id)) {
    MOIRAI_LOG_DEBUG("entity %016llx already recorded",
                     static_cast<unsigned long long>(id));
    return id;
  }
  char u[MOIRAI_URI_LEN], hex[MOIRAI_HEX_LEN];
  moirai_sanitize(u, sizeof(u), uri.c_str());
  moirai_hex(id, hex);
  MOIRAI_LOG_DEBUG("EH id %s type %s store %d uri %s", hex, t,
                   static_cast<int>(store), u);
  DFTracer record(MOIRAI_RECORD_ENTITY, RecordType{});
  record.update("id", hex);
  record.update("type", t);
  record.update("store", static_cast<int>(store));
  record.update("uri", u);
  return id;
}

bool EntityRegistry::relate(MoiraiRelation relation, MoiraiId subject,
                            MoiraiId object) {
  MOIRAI_LOG_TRACE();
  if (!moirai_relation_is_entity(relation) || subject == MOIRAI_NONE ||
      object == MOIRAI_NONE)
    return false;
  char s[MOIRAI_HEX_LEN], o[MOIRAI_HEX_LEN];
  moirai_hex(subject, s);
  moirai_hex(object, o);
  MOIRAI_LOG_DEBUG("ER %s %s %s", s, moirai_relation_name(relation), o);
  DFTracer record(MOIRAI_RECORD_RELATION, RecordType{});
  record.update("relation", static_cast<int>(relation));
  record.update("subject", s);
  record.update("object", o);
  return true;
}
}  // namespace moirai
