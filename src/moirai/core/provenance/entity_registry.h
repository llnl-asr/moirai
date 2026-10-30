#ifndef MOIRAI_CORE_PROVENANCE_ENTITY_REGISTRY_H
#define MOIRAI_CORE_PROVENANCE_ENTITY_REGISTRY_H
#include <moirai/provenance.h>

#include <mutex>
#include <string>
#include <unordered_set>

namespace moirai {
/**
 * The entities and entity types of this process, and their records: each
 * entity (EH) and entity type (ET) is written the first time it is declared,
 * every entity relation (ER) when it is made. Records are dftracer metadata
 * records of moirai's RecordType (include/moirai/moirai.hpp). Used through
 * MoiraiCore, only while tracing.
 */
class EntityRegistry {
 public:
  // The id of (type, key), with type sanitized as it is recorded.
  static MoiraiId id_of(const std::string& type, const std::string& key);

  // Records the type once; false if it already was.
  bool declare_type(const std::string& type, MoiraiRole role,
                    const std::string& description);
  // Records the entity once and returns its id.
  MoiraiId declare(const std::string& type, const std::string& key,
                   MoiraiStore store, const std::string& uri);
  // Records an entity relation; false (nothing written) for an activity
  // relation or a missing entity.
  bool relate(MoiraiRelation relation, MoiraiId subject, MoiraiId object);

 private:
  std::mutex mtx_;
  std::unordered_set<MoiraiId> entities_;
  std::unordered_set<MoiraiId> types_;

  bool first_time(std::unordered_set<MoiraiId>& seen, MoiraiId id);
};
}  // namespace moirai
#endif  // MOIRAI_CORE_PROVENANCE_ENTITY_REGISTRY_H
