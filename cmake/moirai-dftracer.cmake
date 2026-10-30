# dftracer underneath moirai: which dftracer features moirai is built with,
# and where dftracer comes from.
#
# Features (compile time, passed down to dftracer):
#   MOIRAI_ENABLE_HDF5        trace HDF5 (DFTRACER_ENABLE_HDF5)
#   MOIRAI_ENABLE_MPI         trace MPI (DFTRACER_ENABLE_MPI)
#   MOIRAI_DFTRACER_FEATURES  further dftracer features, a list of
#                             HIP CUDA PAPI VARIORUM FTRACING (none by default:
#                             they are about performance, not provenance)
# POSIX/STDIO I/O tracing is always built; MOIRAI_TRACE_IO only sets its
# run-time default. Producer/consumer mode is a run-time setting moirai
# always turns on.
#
# Source (MOIRAI_DFTRACER):
#   FIND     an installed dftracer (dftracer_DIR / CMAKE_PREFIX_PATH), checked
#            for the event-type API and for the HDF5/MPI features asked for
#   BUILD    dftracer built with exactly these features (superbuild), from
#            MOIRAI_DFTRACER_SOURCE_DIR or MOIRAI_DFTRACER_GIT_REPOSITORY/_TAG,
#            then moirai against it; both installed while building into
#            CMAKE_INSTALL_PREFIX (default <build>/install); moirai's build
#            tree, with its tests, is <build>/moirai
#   PACKAGE  the installed dftracer Python package (the dftracer wheel):
#            its include/, lib64/ and bin/, at MOIRAI_DFTRACER_PACKAGE_DIR or
#            found by importing dftracer. Used by moirai's wheels, which then
#            require that wheel; its features are the wheel's.

set(MOIRAI_DFTRACER "FIND" CACHE STRING "Where dftracer comes from: FIND or BUILD")
set_property(CACHE MOIRAI_DFTRACER PROPERTY STRINGS FIND BUILD PACKAGE)
option(MOIRAI_ENABLE_HDF5 "Trace HDF5 through dftracer" OFF)
option(MOIRAI_ENABLE_MPI "Trace MPI through dftracer" OFF)
set(MOIRAI_DFTRACER_FEATURES "" CACHE STRING
    "Further dftracer features: HIP CUDA PAPI VARIORUM FTRACING")

# Feature -> dftracer option.
set(_moirai_feature_HDF5 DFTRACER_ENABLE_HDF5)
set(_moirai_feature_MPI DFTRACER_ENABLE_MPI)
set(_moirai_feature_HIP DFTRACER_ENABLE_HIP_TRACING)
set(_moirai_feature_CUDA DFTRACER_ENABLE_CUDA_TRACING)
set(_moirai_feature_PAPI DFTRACER_ENABLE_PAPI_TRACING)
set(_moirai_feature_VARIORUM DFTRACER_ENABLE_VARIORUM)
set(_moirai_feature_FTRACING DFTRACER_ENABLE_FTRACING)
set(_moirai_all_features HDF5 MPI HIP CUDA PAPI VARIORUM FTRACING)

set(MOIRAI_FEATURES ${MOIRAI_DFTRACER_FEATURES})
if(MOIRAI_ENABLE_HDF5)
    list(APPEND MOIRAI_FEATURES HDF5)
endif()
if(MOIRAI_ENABLE_MPI)
    list(APPEND MOIRAI_FEATURES MPI)
endif()
list(REMOVE_DUPLICATES MOIRAI_FEATURES)
foreach(_f IN LISTS MOIRAI_FEATURES)
    if(NOT _f IN_LIST _moirai_all_features)
        message(FATAL_ERROR "[moirai] unknown dftracer feature '${_f}'; "
                            "known: ${_moirai_all_features}")
    endif()
endforeach()

# The dftracer options for these features: the ones asked for ON, all
# others OFF, and nothing moirai does not use.
set(MOIRAI_DFTRACER_OPTIONS
    -DDFTRACER_BUILD_PYTHON_BINDINGS=OFF
    -DDFTRACER_ENABLE_TESTS=OFF)
foreach(_f IN LISTS _moirai_all_features)
    if(_f IN_LIST MOIRAI_FEATURES)
        list(APPEND MOIRAI_DFTRACER_OPTIONS -D${_moirai_feature_${_f}}=ON)
    else()
        list(APPEND MOIRAI_DFTRACER_OPTIONS -D${_moirai_feature_${_f}}=OFF)
    endif()
endforeach()

if(MOIRAI_DFTRACER STREQUAL "BUILD")
    include(ExternalProject)
    set(MOIRAI_DFTRACER_SOURCE_DIR "" CACHE PATH "dftracer source to build")
    set(MOIRAI_DFTRACER_GIT_REPOSITORY "https://github.com/llnl-asr/dftracer.git"
        CACHE STRING "dftracer repository, when no source directory is given")
    set(MOIRAI_DFTRACER_GIT_TAG "develop" CACHE STRING "dftracer git tag")
    if(MOIRAI_DFTRACER_SOURCE_DIR)
        set(_source SOURCE_DIR ${MOIRAI_DFTRACER_SOURCE_DIR})
    else()
        set(_source GIT_REPOSITORY ${MOIRAI_DFTRACER_GIT_REPOSITORY}
                    GIT_TAG ${MOIRAI_DFTRACER_GIT_TAG} GIT_SHALLOW ON)
    endif()
    # Both are installed while building, dftracer first, into one prefix:
    # moirai next to the dftracer it runs on. Without one given, the build
    # directory's install/ rather than /usr/local.
    if(CMAKE_INSTALL_PREFIX_INITIALIZED_TO_DEFAULT)
        set(CMAKE_INSTALL_PREFIX ${CMAKE_BINARY_DIR}/install CACHE PATH
            "Install prefix of dftracer and moirai" FORCE)
    endif()
    set(_prefix ${CMAKE_INSTALL_PREFIX})
    set(_common_args
        -DCMAKE_INSTALL_PREFIX=${_prefix}
        -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}
        -DCMAKE_C_COMPILER=${CMAKE_C_COMPILER}
        -DCMAKE_CXX_COMPILER=${CMAKE_CXX_COMPILER})
    message(STATUS "[moirai] building dftracer (${MOIRAI_DFTRACER_OPTIONS})")
    # dftracer builds in two passes, as its setup.py does: its dependencies
    # first (DFTRACER_INSTALL_DEPENDENCIES=ON builds and installs only them
    # into the prefix), then dftracer itself against them.
    ExternalProject_Add(dftracer_dependencies
        ${_source}
        PREFIX ${CMAKE_BINARY_DIR}/dftracer-build
        BINARY_DIR ${CMAKE_BINARY_DIR}/dftracer-build/dependencies
        CMAKE_ARGS ${_common_args} ${MOIRAI_DFTRACER_OPTIONS}
            -DDFTRACER_INSTALL_DEPENDENCIES=ON
        INSTALL_COMMAND "")
    ExternalProject_Get_Property(dftracer_dependencies SOURCE_DIR)
    ExternalProject_Add(dftracer
        SOURCE_DIR ${SOURCE_DIR}
        DOWNLOAD_COMMAND ""
        PREFIX ${CMAKE_BINARY_DIR}/dftracer-build
        BINARY_DIR ${CMAKE_BINARY_DIR}/dftracer-build/dftracer
        CMAKE_ARGS ${_common_args} ${MOIRAI_DFTRACER_OPTIONS}
            -DDFTRACER_INSTALL_DEPENDENCIES=OFF
            -DCMAKE_PREFIX_PATH=${_prefix}
        DEPENDS dftracer_dependencies)
    # moirai itself, against the dftracer just built.
    get_cmake_property(_vars CACHE_VARIABLES)
    set(_moirai_args)
    foreach(_v IN LISTS _vars)
        if(_v MATCHES "^(MOIRAI_|CMAKE_BUILD_TYPE$|CMAKE_INSTALL_PREFIX$|CMAKE_C_COMPILER$|CMAKE_CXX_COMPILER$|Python_EXECUTABLE$|pybind11_DIR$)"
           AND NOT _v STREQUAL "MOIRAI_DFTRACER")
            list(APPEND _moirai_args "-D${_v}=${${_v}}")
        endif()
    endforeach()
    ExternalProject_Add(moirai_project
        SOURCE_DIR ${PROJECT_SOURCE_DIR}
        BINARY_DIR ${CMAKE_BINARY_DIR}/moirai
        CMAKE_ARGS ${_moirai_args}
            -DMOIRAI_DFTRACER=FIND
            -DCMAKE_PREFIX_PATH=${_prefix}
            -DCMAKE_INSTALL_PREFIX=${_prefix}
        BUILD_ALWAYS ON
        DEPENDS dftracer)
    set(MOIRAI_SUPERBUILD TRUE)
    return()
endif()

if(MOIRAI_DFTRACER STREQUAL "PACKAGE")
    set(MOIRAI_DFTRACER_PACKAGE_DIR "" CACHE PATH
        "The dftracer Python package (site-packages/dftracer); found by importing it when empty")
    if(NOT MOIRAI_DFTRACER_PACKAGE_DIR)
        find_package(Python COMPONENTS Interpreter REQUIRED)
        execute_process(
            COMMAND ${Python_EXECUTABLE} -c
                "import dftracer, os; print(os.path.dirname(dftracer.__file__))"
            OUTPUT_VARIABLE MOIRAI_DFTRACER_PACKAGE_DIR
            OUTPUT_STRIP_TRAILING_WHITESPACE RESULT_VARIABLE _rc)
        if(NOT _rc EQUAL 0)
            message(FATAL_ERROR "[moirai] MOIRAI_DFTRACER=PACKAGE: cannot import "
                                "dftracer with ${Python_EXECUTABLE}")
        endif()
    endif()
    set(_pkg ${MOIRAI_DFTRACER_PACKAGE_DIR})
    # The package's libraries and executables as dftracer's own targets.
    foreach(_lib dftracer_core dftracer_core_dbg cpp-logger)
        find_library(_path_${_lib} NAMES ${_lib} PATHS ${_pkg}/lib64 ${_pkg}/lib
                     NO_DEFAULT_PATH REQUIRED)
        add_library(${_lib} SHARED IMPORTED)
        set_target_properties(${_lib} PROPERTIES
            IMPORTED_LOCATION ${_path_${_lib}}
            INTERFACE_INCLUDE_DIRECTORIES ${_pkg}/include)
    endforeach()
    find_program(_path_dftracer_service NAMES dftracer_service
                 PATHS ${_pkg}/bin NO_DEFAULT_PATH REQUIRED)
    # The dftracer wheel ships only the release service; the _dbg one, when
    # there is none, runs it too (only the service's own logging is lost).
    find_program(_path_dftracer_service_dbg NAMES dftracer_service_dbg
                 PATHS ${_pkg}/bin NO_DEFAULT_PATH)
    if(NOT _path_dftracer_service_dbg)
        set(_path_dftracer_service_dbg ${_path_dftracer_service})
        set(MOIRAI_SERVICE_DBG_NAME dftracer_service)
    endif()
    foreach(_exe dftracer_service dftracer_service_dbg)
        add_executable(${_exe} IMPORTED)
        set_target_properties(${_exe} PROPERTIES IMPORTED_LOCATION ${_path_${_exe}})
    endforeach()
    # The wheel's features: no HDF5 or MPI (dftracer's wheels build without).
    foreach(_f HDF5 MPI)
        set(MOIRAI_HAS_${_f} 0)
        if(_f IN_LIST MOIRAI_FEATURES)
            message(FATAL_ERROR "[moirai] MOIRAI_ENABLE_${_f} needs a dftracer "
                                "built with it; the dftracer package has none")
        endif()
    endforeach()
    set(DFTRACER_VERSION "(package)")
    set(dftracer_DIR ${_pkg})
elseif(MOIRAI_DFTRACER STREQUAL "FIND")
    find_package(dftracer REQUIRED)
else()
    message(FATAL_ERROR "[moirai] MOIRAI_DFTRACER is FIND, BUILD or PACKAGE, "
                        "not '${MOIRAI_DFTRACER}'")
endif()

# The event-type API moirai's types are defined with.
include(CheckCXXSourceCompiles)
get_target_property(_dft_includes dftracer_core INTERFACE_INCLUDE_DIRECTORIES)
set(CMAKE_REQUIRED_INCLUDES ${_dft_includes})
set(CMAKE_REQUIRED_FLAGS "-std=c++17")
check_cxx_source_compiles("
#include <dftracer/dftracer.h>
struct T : dftracer::EventType { static constexpr bool aggregatable = false; };
int main() {
  DFTracerEventType t = dftracer::event_type_of<T>();
  return t.aggregatable;
}" MOIRAI_DFTRACER_HAS_EVENT_TYPES)
unset(CMAKE_REQUIRED_INCLUDES)
unset(CMAKE_REQUIRED_FLAGS)
if(NOT MOIRAI_DFTRACER_HAS_EVENT_TYPES)
    message(FATAL_ERROR "[moirai] dftracer at ${dftracer_DIR} has no event-type "
                        "API (dftracer::EventType); build a newer dftracer or "
                        "use -DMOIRAI_DFTRACER=BUILD")
endif()

# What the found dftracer traces must cover what moirai asks for. Only
# HDF5 and MPI are recorded in its package; the rest cannot be checked.
if(MOIRAI_DFTRACER STREQUAL "FIND")
foreach(_f HDF5 MPI)
    if(DFTRACER_INCLUDE_${_f})
        set(MOIRAI_HAS_${_f} 1)
    else()
        set(MOIRAI_HAS_${_f} 0)
    endif()
    if(_f IN_LIST MOIRAI_FEATURES AND NOT MOIRAI_HAS_${_f})
        message(FATAL_ERROR "[moirai] MOIRAI_ENABLE_${_f} is ON but dftracer at "
                            "${dftracer_DIR} was built without ${_f}; use "
                            "-DMOIRAI_DFTRACER=BUILD or a dftracer built with "
                            "-D${_moirai_feature_${_f}}=ON")
    endif()
endforeach()
endif()
foreach(_f IN LISTS MOIRAI_FEATURES)
    if(NOT _f MATCHES "^(HDF5|MPI)$")
        message(STATUS "[moirai] assuming dftracer at ${dftracer_DIR} was built "
                       "with ${_f} (its package does not record it)")
    endif()
endforeach()
message(STATUS "[moirai] dftracer ${DFTRACER_VERSION} at ${dftracer_DIR}: "
               "HDF5=${MOIRAI_HAS_HDF5} MPI=${MOIRAI_HAS_MPI}")
