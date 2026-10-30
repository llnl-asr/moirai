#ifndef MOIRAI_PROVENANCE_H
#define MOIRAI_PROVENANCE_H
/*
 * Provenance definitions shared by moirai's C, C++ and Python APIs.
 *
 * An entity is a typed instance of something an application works with (a
 * file, a dataset shard, a checkpoint, a protein structure, a GPU buffer).
 *
 *   identity    MoiraiId        64-bit FNV-1a of (type, key); written as
 *                               exactly 16 lowercase hex characters.
 *   type        string (MOIRAI_TYPE_LEN), application-defined
 *   store       MoiraiStore     where the instance lives
 *   uri         string (MOIRAI_URI_LEN), unique within the application
 *   role        MoiraiRole      per entity TYPE (input, output, ...)
 *   description string (MOIRAI_DESC_LEN), per entity TYPE
 *   relation    MoiraiRelation  activity -> entity and entity -> entity
 *
 * Strings are truncated and restricted to a JSON-safe character set
 * (moirai_sanitize). Values, ids and names are those of dftracer's former
 * provenance API, so traces read the same.
 *
 * Trace records (dftracer metadata records on moirai's layer):
 *   EH  {"id":"<16-hex>","type":"<type>","store":<int>,"uri":"<uri>"}
 *   ET  {"type":"<type>","role":<int>,"description":"<text>"}
 *   ER  {"relation":<int>,"subject":"<16-hex>","object":"<16-hex>"}
 * Activities are dftracer events on moirai's layer, never aggregated, with
 *   "relations":{"used":["<16-hex>",...],"generated":[...],...}
 */
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef uint64_t MoiraiId;

/* String capacities, including the terminating NUL. */
#define MOIRAI_TYPE_LEN 32
#define MOIRAI_URI_LEN 256
#define MOIRAI_DESC_LEN 256
/* 16 hex digits + NUL. */
#define MOIRAI_HEX_LEN 17

#define MOIRAI_NONE ((MoiraiId)0)

/* dftracer layer ("type" column) of moirai's events and records:
 * DFTRACER_TRACE_TYPE_EXTERNAL + 0. */
#define MOIRAI_LAYER 128
/* Category of activity events. */
#define MOIRAI_CATEGORY "moirai"
/* Record names. */
#define MOIRAI_RECORD_ENTITY "EH"
#define MOIRAI_RECORD_ENTITY_TYPE "ET"
#define MOIRAI_RECORD_RELATION "ER"
/* Event arg holding an activity's relations. */
#define MOIRAI_RELATIONS_ARG "relations"

/* Where an entity instance lives. */
typedef enum {
  MOIRAI_STORE_MEMORY = 0,
  MOIRAI_STORE_GPU_MEMORY = 1,
  MOIRAI_STORE_LOCAL_DISK = 2,
  MOIRAI_STORE_PARALLEL_FS = 3,
  MOIRAI_STORE_BURST_BUFFER = 4,
  MOIRAI_STORE_OBJECT_STORE = 5,
  MOIRAI_STORE_DATABASE = 6,
  MOIRAI_STORE_NETWORK = 7,
  MOIRAI_STORE_OTHER = 8
} MoiraiStore;

/* Role of an entity TYPE in the workflow. */
typedef enum {
  MOIRAI_ROLE_UNKNOWN = 0,
  MOIRAI_ROLE_INPUT = 1,        /* enters the workflow from outside */
  MOIRAI_ROLE_OUTPUT = 2,       /* a deliverable / scientific artifact */
  MOIRAI_ROLE_INTERMEDIATE = 3, /* produced and consumed inside it */
  MOIRAI_ROLE_PARAMETER = 4,    /* configuration, seeds, model settings */
  MOIRAI_ROLE_REFERENCE = 5     /* versioned reference data */
} MoiraiRole;

/* An artifact is content too large for a trace, kept next to it. An entity's
 * uri holds its address, MOIRAI_ARTIFACT_SCHEME + 16 hex digits, as every id
 * in a trace, so a trace holds only the key. Equal content has the same key;
 * the key is of a sample of large content, so it is not a proof of equality
 * across runs. */
#define MOIRAI_ARTIFACT_SCHEME "artifact://"
/* Scheme + 16 hex digits + NUL. */
#define MOIRAI_ARTIFACT_URI_LEN 28

/* How long an artifact's content outlives the run, which decides what is kept
 * of it. */
typedef enum {
  MOIRAI_ARTIFACT_TRANSIENT = 0, /* it goes away: the content is stored */
  MOIRAI_ARTIFACT_PERSISTENT = 1 /* it stays: only a link to it is stored */
} MoiraiArtifactLifetime;

/* Relations. Values < 16 relate an ACTIVITY to an entity (activity args);
 * values >= 16 relate two ENTITIES (ER records). */
typedef enum {
  /* activity -> entity (W3C PROV style) */
  MOIRAI_REL_USED = 0,        /* the activity consumed the entity */
  MOIRAI_REL_GENERATED = 1,   /* the activity produced the entity */
  MOIRAI_REL_INVALIDATED = 2, /* the activity ended the entity */
  MOIRAI_REL_UPDATED = 3,     /* the activity modified it in place */
  /* entity -> entity */
  MOIRAI_REL_DERIVED_FROM = 16,      /* subject was derived from object */
  MOIRAI_REL_REVISION_OF = 17,       /* subject is a newer version of object */
  MOIRAI_REL_CONTAINS = 18,          /* subject has object as a member */
  MOIRAI_REL_PART_OF = 19,           /* subject is part of object */
  MOIRAI_REL_SPECIALIZATION_OF = 20, /* subject is a kind of object */
  MOIRAI_REL_ALTERNATE_OF = 21,      /* same thing, another representation */
  MOIRAI_REL_DEPENDS_ON = 22         /* subject requires object */
} MoiraiRelation;

static inline int moirai_relation_is_activity(MoiraiRelation r) {
  return r >= MOIRAI_REL_USED && r <= MOIRAI_REL_UPDATED;
}
static inline int moirai_relation_is_entity(MoiraiRelation r) {
  return r >= MOIRAI_REL_DERIVED_FROM && r <= MOIRAI_REL_DEPENDS_ON;
}

/* Stable relation names (part of the trace format). */
static inline const char* moirai_relation_name(MoiraiRelation r) {
  switch (r) {
    case MOIRAI_REL_USED:
      return "used";
    case MOIRAI_REL_GENERATED:
      return "generated";
    case MOIRAI_REL_INVALIDATED:
      return "invalidated";
    case MOIRAI_REL_UPDATED:
      return "updated";
    case MOIRAI_REL_DERIVED_FROM:
      return "derived_from";
    case MOIRAI_REL_REVISION_OF:
      return "revision_of";
    case MOIRAI_REL_CONTAINS:
      return "contains";
    case MOIRAI_REL_PART_OF:
      return "part_of";
    case MOIRAI_REL_SPECIALIZATION_OF:
      return "specialization_of";
    case MOIRAI_REL_ALTERNATE_OF:
      return "alternate_of";
    case MOIRAI_REL_DEPENDS_ON:
      return "depends_on";
  }
  return "related";
}

/* JSON-safe character set; anything else becomes '_'. */
static inline int moirai_safe_char(char c) {
  if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
      (c >= '0' && c <= '9'))
    return 1;
  switch (c) {
    case '_':
    case '-':
    case '.':
    case ':':
    case '/':
    case '@':
    case '+':
    case '=':
    case ',':
    case '~':
    case ' ':
      return 1;
    default:
      return 0;
  }
}

/* Copy src into dst[cap], truncated, with the safe character set. */
static inline void moirai_sanitize(char* dst, size_t cap, const char* src) {
  size_t i = 0;
  if (cap == 0) return;
  if (src != NULL)
    for (; src[i] != '\0' && i + 1 < cap; ++i)
      dst[i] = moirai_safe_char(src[i]) ? src[i] : '_';
  dst[i] = '\0';
}

/* 64-bit FNV-1a of type, a 0x1f separator, and key. The same in every
 * language and process; 0 is reserved for MOIRAI_NONE. */
static inline MoiraiId moirai_hash(const char* type, const char* key) {
  uint64_t h = 1469598103934665603ULL;
  const unsigned char* p;
  for (p = (const unsigned char*)(type ? type : ""); *p; ++p) {
    h ^= *p;
    h *= 1099511628211ULL;
  }
  h ^= 0x1fu;
  h *= 1099511628211ULL;
  for (p = (const unsigned char*)(key ? key : ""); *p; ++p) {
    h ^= *p;
    h *= 1099511628211ULL;
  }
  return h == MOIRAI_NONE ? 1 : h;
}

/* An id as exactly 16 lowercase hex digits into out[MOIRAI_HEX_LEN]. */
static inline void moirai_hex(MoiraiId id, char* out) {
  static const char digits[] = "0123456789abcdef";
  int i;
  for (i = 15; i >= 0; --i) {
    out[i] = digits[id & 0xfu];
    id >>= 4;
  }
  out[16] = '\0';
}

#ifdef __cplusplus
}
#endif
#endif /* MOIRAI_PROVENANCE_H */
