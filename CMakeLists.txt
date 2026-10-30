cmake_minimum_required(VERSION 3.24)
file(STRINGS ${CMAKE_CURRENT_SOURCE_DIR}/VERSION MOIRAI_VERSION LIMIT_COUNT 1)
project(moirai VERSION ${MOIRAI_VERSION} LANGUAGES C CXX)

# moirai: data provenance for HPC applications, traced by dftracer
# underneath it (see include/moirai/moirai.h and docs/design.rst).

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
include(GNUInstallDirs)

option(MOIRAI_TRACE_IO "Trace POSIX/STDIO I/O by default (MOIRAI_TRACE_IO at run time)" ON)
option(MOIRAI_BUILD_PYTHON "Build the Python API" ON)
option(MOIRAI_ENABLE_TESTS "Build and register the tests" OFF)
option(MOIRAI_WARNINGS_AS_ERRORS "Promote warnings to errors" OFF)
# The wheel layout: everything in the moirai package (site-packages/moirai),
# next to the dftracer wheel's package it runs on (site-packages/dftracer).
option(MOIRAI_WHEEL "Install as moirai's Python wheel" OFF)

include(${PROJECT_SOURCE_DIR}/cmake/moirai-dftracer.cmake)
if(MOIRAI_SUPERBUILD)
    return()
endif()
include(${PROJECT_SOURCE_DIR}/cmake/moirai-artifacts.cmake)

if(MOIRAI_TRACE_IO)
    set(MOIRAI_DEFAULT_TRACE_IO 1)
else()
    set(MOIRAI_DEFAULT_TRACE_IO 0)
endif()
string(REPLACE ";" "," MOIRAI_DFTRACER_FEATURES_TEXT "${MOIRAI_DFTRACER_FEATURES}")
set(MOIRAI_DFTRACER_FEATURES "${MOIRAI_DFTRACER_FEATURES_TEXT}")
configure_file(${PROJECT_SOURCE_DIR}/cmake/moirai_config.h.in
               ${PROJECT_BINARY_DIR}/include/moirai/moirai_config.h @ONLY)

set(MOIRAI_WARNINGS -Wall -Wextra -pedantic)
if(MOIRAI_WARNINGS_AS_ERRORS)
    list(APPEND MOIRAI_WARNINGS -Werror)
endif()
set(CMAKE_BUILD_RPATH_USE_ORIGIN ON)
if(MOIRAI_WHEEL)
    # site-packages/moirai/{lib64,bin,include} and the package at the root;
    # dftracer's libraries are the dftracer wheel's, found relative to ours.
    set(CMAKE_INSTALL_LIBDIR moirai/lib64)
    set(CMAKE_INSTALL_BINDIR moirai/bin)
    set(CMAKE_INSTALL_INCLUDEDIR moirai/include)
    set(MOIRAI_PYTHON_INSTALL_DIR . CACHE STRING "" FORCE)
    set(MOIRAI_RPATH_LIB "$ORIGIN;$ORIGIN/../../dftracer/lib64;$ORIGIN/../../dftracer/lib")
    set(MOIRAI_RPATH_BIN "$ORIGIN/../lib64;$ORIGIN/../../dftracer/lib64;$ORIGIN/../../dftracer/lib")
    set(MOIRAI_RPATH_PY "$ORIGIN/lib64;$ORIGIN/../dftracer/lib64;$ORIGIN/../dftracer/lib")
    # moirai-service runs the dftracer wheel's service, relative to itself.
    set(MOIRAI_SERVICE_RELATIVE "../../dftracer/bin/")
else()
    set(CMAKE_INSTALL_RPATH "${CMAKE_INSTALL_PREFIX}/${CMAKE_INSTALL_LIBDIR}")
    set(CMAKE_INSTALL_RPATH_USE_LINK_PATH ON)
endif()

# cpp-logger, for the _dbg builds' logging (as dftracer's); dftracer's
# package sits next to it (MOIRAI_DFTRACER=PACKAGE has made it already).
if(NOT TARGET cpp-logger)
    find_package(cpp-logger 2.0.0 REQUIRED
                 HINTS ${dftracer_DIR}/../cpp-logger)
endif()

set(MOIRAI_CORE_SRC
    src/moirai/core/common/logging.cpp
    src/moirai/core/utils/configuration_manager.cpp
    src/moirai/core/provenance/entity_registry.cpp
    src/moirai/core/artifact/artifact_store.cpp
    src/moirai/core/moirai_main.cpp
    src/moirai/core/moirai.cpp)
set(MOIRAI_SERVICE_SRC
    src/moirai/core/common/logging.cpp
    src/moirai/core/utils/configuration_manager.cpp
    src/moirai/service/moirai_service.cpp
    src/moirai/service/main.cpp)

if(MOIRAI_BUILD_PYTHON)
    find_package(Python COMPONENTS Interpreter Development.Module REQUIRED)
    if(NOT pybind11_DIR)
        execute_process(
            COMMAND ${Python_EXECUTABLE} -m pybind11 --cmakedir
            OUTPUT_VARIABLE pybind11_DIR OUTPUT_STRIP_TRAILING_WHITESPACE)
    endif()
    find_package(pybind11 CONFIG REQUIRED)
    set(MOIRAI_PYTHON_DIR ${PROJECT_BINARY_DIR}/python)
    set(MOIRAI_PYTHON_INSTALL_DIR
        ${CMAKE_INSTALL_LIBDIR}/python${Python_VERSION_MAJOR}.${Python_VERSION_MINOR}/site-packages
        CACHE STRING "Where the moirai Python package is installed")
endif()

# Every target twice, as dftracer's: the release build, with all logging
# compiled out, on dftracer_core; and the _dbg build, with moirai's logging
# (cpp-logger, MOIRAI_DEBUG) compiled in, on dftracer_core_dbg.
foreach(_dbg "" "_dbg")
    # libmoirai: the C++ actors and their C connector.
    add_library(moirai${_dbg} SHARED ${MOIRAI_CORE_SRC})
    target_include_directories(moirai${_dbg}
        PUBLIC
            $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/include>
            $<BUILD_INTERFACE:${PROJECT_BINARY_DIR}/include>
            $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
        PRIVATE ${PROJECT_SOURCE_DIR}/src)
    target_link_libraries(moirai${_dbg} PUBLIC dftracer_core${_dbg})
    if(MOIRAI_HAS_ARTIFACT_STORE)
        target_include_directories(moirai${_dbg} SYSTEM PRIVATE
            ${MOIRAI_DFTRACER_UTILS_INCLUDE_DIR} ${MOIRAI_ROCKSDB_INCLUDE_DIR})
        target_link_libraries(moirai${_dbg} PRIVATE ${MOIRAI_DFTRACER_UTILS_LIBRARY})
        target_compile_definitions(moirai${_dbg} PRIVATE ROCKSDB_USE_RTTI)
    endif()
    target_compile_options(moirai${_dbg} PRIVATE ${MOIRAI_WARNINGS})
    set_target_properties(moirai${_dbg} PROPERTIES
        VERSION ${PROJECT_VERSION} SOVERSION ${PROJECT_VERSION_MAJOR})

    # moirai-service: dftracer_service configured for provenance.
    add_executable(moirai-service${_dbg} ${MOIRAI_SERVICE_SRC})
    target_include_directories(moirai-service${_dbg} PRIVATE
        ${PROJECT_SOURCE_DIR}/src ${PROJECT_SOURCE_DIR}/include
        ${PROJECT_BINARY_DIR}/include)
    target_compile_definitions(moirai-service${_dbg} PRIVATE
        MOIRAI_DFTRACER_SERVICE_PATH="$<TARGET_FILE:dftracer_service${_dbg}>")
    if(MOIRAI_SERVICE_RELATIVE)
        set(_service_name dftracer_service${_dbg})
        if(_dbg AND MOIRAI_SERVICE_DBG_NAME)
            set(_service_name ${MOIRAI_SERVICE_DBG_NAME})
        endif()
        target_compile_definitions(moirai-service${_dbg} PRIVATE
            MOIRAI_DFTRACER_SERVICE_RELATIVE="${MOIRAI_SERVICE_RELATIVE}${_service_name}")
    endif()
    target_compile_options(moirai-service${_dbg} PRIVATE ${MOIRAI_WARNINGS})

    # The Python binding, in <build>/python/moirai next to the package.
    if(MOIRAI_BUILD_PYTHON)
        pybind11_add_module(_moirai${_dbg} src/moirai/python/moirai_py.cpp)
        target_link_libraries(_moirai${_dbg} PRIVATE moirai${_dbg})
        target_compile_definitions(_moirai${_dbg} PRIVATE
            MOIRAI_PY_MODULE=_moirai${_dbg})
        set_target_properties(_moirai${_dbg} PROPERTIES
            LIBRARY_OUTPUT_DIRECTORY ${MOIRAI_PYTHON_DIR}/moirai)
        install(TARGETS _moirai${_dbg}
                DESTINATION ${MOIRAI_PYTHON_INSTALL_DIR}/moirai)
        list(APPEND MOIRAI${_dbg}_TARGETS _moirai${_dbg})
    endif()
    list(APPEND MOIRAI${_dbg}_TARGETS moirai${_dbg} moirai-service${_dbg})
    if(MOIRAI_WHEEL)
        set_target_properties(moirai${_dbg} PROPERTIES INSTALL_RPATH "${MOIRAI_RPATH_LIB}")
        set_target_properties(moirai-service${_dbg} PROPERTIES INSTALL_RPATH "${MOIRAI_RPATH_BIN}")
        if(MOIRAI_BUILD_PYTHON)
            set_target_properties(_moirai${_dbg} PROPERTIES INSTALL_RPATH "${MOIRAI_RPATH_PY}")
        endif()
    endif()
endforeach()
foreach(_target IN LISTS MOIRAI_dbg_TARGETS)
    target_compile_definitions(${_target} PRIVATE MOIRAI_DEBUG)
    target_compile_options(${_target} PRIVATE -g -O0)
    target_link_libraries(${_target} PRIVATE cpp-logger ${CMAKE_DL_LIBS})
endforeach()

if(MOIRAI_BUILD_PYTHON)
    file(GLOB_RECURSE _moirai_py CONFIGURE_DEPENDS
         RELATIVE ${PROJECT_SOURCE_DIR}/python ${PROJECT_SOURCE_DIR}/python/moirai/*.py)
    foreach(_f IN LISTS _moirai_py)
        configure_file(${PROJECT_SOURCE_DIR}/python/${_f} ${MOIRAI_PYTHON_DIR}/${_f} COPYONLY)
        get_filename_component(_dir ${_f} DIRECTORY)
        install(FILES ${PROJECT_SOURCE_DIR}/python/${_f}
                DESTINATION ${MOIRAI_PYTHON_INSTALL_DIR}/${_dir})
    endforeach()
endif()

install(TARGETS moirai moirai_dbg
        LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(TARGETS moirai-service moirai-service_dbg
        RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
install(DIRECTORY ${PROJECT_SOURCE_DIR}/include/moirai
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(FILES ${PROJECT_BINARY_DIR}/include/moirai/moirai_config.h
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/moirai)

if(MOIRAI_ENABLE_TESTS)
    enable_testing()
    add_subdirectory(test)
endif()
