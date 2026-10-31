#ifndef MOIRAI_MOIRAI_H
#define MOIRAI_MOIRAI_H
/*
 * moirai: data provenance for HPC applications, traced by dftracer.
 *
 * moirai runs dftracer underneath it, configured for provenance: started by
 * moirai_initialize, always in producer/consumer mode (events go to a
 * dftracer_service started with moirai-service, or to a spill file when none
 * is running), with POSIX/STDIO I/O traced or not (MOIRAI_TRACE_IO), and
 * HDF5/MPI as moirai was built.
 *
 * Run-time configuration is moirai's; it is translated into dftracer's when
 * moirai starts, so an application never sets DFTRACER_*:
 *   MOIRAI_ENABLE            0 turns tracing off (default 1)
 *   MOIRAI_LOG_FILE          trace prefix, shared with moirai-service
 *   MOIRAI_TRACE_IO          1/0: trace POSIX/STDIO I/O (default: build)
 *   MOIRAI_DFTRACER_SERVICE  dftracer_service binary for moirai-service
 * Every other MOIRAI_<X> is dftracer's DFTRACER_<X>, e.g. MOIRAI_DATA_DIR
 * (':'-separated directories whose I/O is traced, each also by its real path
 * when that differs; default all), MOIRAI_SERVICE_SHM (the service's ring),
 * MOIRAI_CONFIGURATION (a dftracer YAML file),
 * MOIRAI_LOG_LEVEL (also moirai's own, in the _dbg build).
 *
 * This is the C connector of moirai.hpp: every call goes to the same C++
 * actors.
 */
#include <moirai/moirai_config.h>
#include <moirai/provenance.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Configure dftracer for provenance and start tracing; log_file overrides
 * MOIRAI_LOG_FILE (NULL: keep it). Returns 1 when tracing, 0 when disabled.
 * Calling it again does nothing. */
int moirai_initialize(const char* log_file);
/* Stop tracing and flush. */
void moirai_finalize(void);
/* 1 between moirai_initialize and moirai_finalize when tracing is on. */
int moirai_is_active(void);

/* Describe an entity type once per process (an ET record). */
void moirai_entity_type(const char* type, MoiraiRole role,
                        const char* description);
/* Declare an entity: (type, key) -> id, recorded once per process (an EH
 * record). key is hashed, never stored; uri may be NULL. The id is returned
 * also when tracing is off. */
MoiraiId moirai_entity(const char* type, const char* key, MoiraiStore store,
                       const char* uri);
/* Relate two entities (an ER record); relation is an entity relation. */
void moirai_relate(MoiraiRelation relation, MoiraiId subject, MoiraiId object);

/* An activity (moirai::Activity): one event from begin to end, relating it
 * to entities. name must outlive the activity. */
struct MoiraiActivityData {
  void* activity;
};
struct MoiraiActivityData* moirai_activity_begin(const char* name);
/* relation is an activity relation (USED, GENERATED, INVALIDATED, UPDATED);
 * others are ignored. */
void moirai_activity_relate(struct MoiraiActivityData* data,
                            MoiraiRelation relation, MoiraiId entity);
/* Declare (type, key) and relate it in one call; returns its id. */
MoiraiId moirai_activity_relate_entity(struct MoiraiActivityData* data,
                                       MoiraiRelation relation,
                                       const char* type, const char* key,
                                       MoiraiStore store, const char* uri);
void moirai_activity_end(struct MoiraiActivityData* data);
void moirai_activity_cleanup(struct MoiraiActivityData** data);

/* Content kept next to the trace, in <log file>.artifacts (moirai::Artifact);
 * give the uri to moirai_entity. uri has MOIRAI_ARTIFACT_URI_LEN bytes; each
 * returns 1, or 0 if there is no such content. */
int moirai_artifact(const void* data, size_t size, char* uri);
/* A file: its content stored if transient, a link to it if persistent. */
int moirai_artifact_file(const char* path, MoiraiArtifactLifetime lifetime,
                         char* uri);
/* The content at uri, malloc'ed into *data; log_file is the run's trace prefix
 * (NULL: this one). */
int moirai_artifact_read(const char* uri, void** data, size_t* size,
                         const char* log_file);

/* Activities scoped to a C block, as dftracer's regions:
 * MOIRAI_C_ACTIVITY_START(name) ... MOIRAI_C_ACTIVITY_END(name), or ended when
 * the block is left; MOIRAI_C_FUNCTION_START() is the function's. */
#if defined(__GNUC__) || defined(__clang__)
#define MOIRAI_C_ACTIVITY_CLEANUP \
  __attribute__((cleanup(moirai_activity_cleanup)))
#else
#define MOIRAI_C_ACTIVITY_CLEANUP
#endif
#define MOIRAI_C_FUNCTION_START()                                  \
  struct MoiraiActivityData* moirai_fn MOIRAI_C_ACTIVITY_CLEANUP = \
      moirai_activity_begin(__func__)
#define MOIRAI_C_FUNCTION_END()   \
  moirai_activity_end(moirai_fn); \
  moirai_fn = NULL
#define MOIRAI_C_ACTIVITY_START(name)                                  \
  struct MoiraiActivityData* moirai_##name MOIRAI_C_ACTIVITY_CLEANUP = \
      moirai_activity_begin(#name)
#define MOIRAI_C_ACTIVITY_END(name)   \
  moirai_activity_end(moirai_##name); \
  moirai_##name = NULL
#define MOIRAI_C_ACTIVITY_RELATE(name, relation, entity) \
  moirai_activity_relate(moirai_##name, relation, entity)
#define MOIRAI_C_ACTIVITY_USED(name, entity) \
  moirai_activity_relate(moirai_##name, MOIRAI_REL_USED, entity)
#define MOIRAI_C_ACTIVITY_GENERATED(name, entity) \
  moirai_activity_relate(moirai_##name, MOIRAI_REL_GENERATED, entity)
#define MOIRAI_C_ACTIVITY_INVALIDATED(name, entity) \
  moirai_activity_relate(moirai_##name, MOIRAI_REL_INVALIDATED, entity)
#define MOIRAI_C_ACTIVITY_UPDATED(name, entity) \
  moirai_activity_relate(moirai_##name, MOIRAI_REL_UPDATED, entity)

#ifdef __cplusplus
}
#endif
#endif /* MOIRAI_MOIRAI_H */
