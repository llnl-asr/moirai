# The artifact store: RocksDB, through dftracer-utils (RocksDatabase in
# libdftracer_utils_utilities). dftracer-utils installs no CMake package for
# this, so it is found here, next to the dftracer moirai builds on:
#
#   MOIRAI_DFTRACER_UTILS_PREFIX  an install prefix or the dftracer wheel's
#                                 package directory (default: searched)
#   MOIRAI_ROCKSDB_INCLUDE_DIR    the RocksDB headers, if not in that prefix
#
# Without them moirai still builds: artifacts are addressed, not stored.
option(MOIRAI_ARTIFACTS "Store artifacts (needs dftracer-utils)" ON)
set(MOIRAI_DFTRACER_UTILS_PREFIX "" CACHE PATH "dftracer-utils install prefix")

set(_hints ${MOIRAI_DFTRACER_UTILS_PREFIX})
if(dftracer_DIR)
    get_filename_component(_dft_prefix "${dftracer_DIR}/../../.." ABSOLUTE)
    list(APPEND _hints ${_dft_prefix})
endif()
find_package(Python COMPONENTS Interpreter QUIET)
if(Python_EXECUTABLE)
    execute_process(
        COMMAND ${Python_EXECUTABLE} -c
                "import importlib.util as u; s = u.find_spec('dftracer'); print(s.submodule_search_locations[0] if s else '')"
        OUTPUT_VARIABLE _wheel OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
    if(_wheel)
        list(APPEND _hints ${_wheel})
    endif()
endif()

set(MOIRAI_HAS_ARTIFACT_STORE 0)
if(MOIRAI_ARTIFACTS)
    find_library(MOIRAI_DFTRACER_UTILS_LIBRARY dftracer_utils_utilities
                 HINTS ${_hints} PATH_SUFFIXES lib lib64)
    find_path(MOIRAI_DFTRACER_UTILS_INCLUDE_DIR
              dftracer/utils/index/store/database.h
              HINTS ${_hints} PATH_SUFFIXES include)
    find_path(MOIRAI_ROCKSDB_INCLUDE_DIR rocksdb/db.h
              HINTS ${_hints} PATH_SUFFIXES include)
    if(MOIRAI_DFTRACER_UTILS_LIBRARY AND MOIRAI_DFTRACER_UTILS_INCLUDE_DIR
       AND MOIRAI_ROCKSDB_INCLUDE_DIR)
        set(MOIRAI_HAS_ARTIFACT_STORE 1)
        # dftracer-utils' headers are C++20; moirai's own stay C++17.
        set_property(SOURCE src/moirai/core/artifact/artifact_store.cpp
                     APPEND PROPERTY COMPILE_OPTIONS -std=c++20)
        message(STATUS "[moirai] artifact store: ${MOIRAI_DFTRACER_UTILS_LIBRARY}")
    else()
        message(WARNING "[moirai] no dftracer-utils with RocksDB headers: "
                        "artifacts are addressed, not stored. Set "
                        "MOIRAI_DFTRACER_UTILS_PREFIX or MOIRAI_ROCKSDB_INCLUDE_DIR.")
    endif()
endif()
