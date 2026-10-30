# One provenance scenario through each API (C, C++, Python), with the
# release and the _dbg build, run as a moirai user runs it -- MOIRAI_*
# settings only, through moirai-service or its spill file -- and checked by
# check_provenance.py.
find_package(Python COMPONENTS Interpreter REQUIRED)

# Runs under valgrind (label "valgrind"), when it is installed.
find_program(MOIRAI_VALGRIND valgrind)
if(MOIRAI_VALGRIND)
    set(_valgrind_default ON)
else()
    set(_valgrind_default OFF)
endif()
option(MOIRAI_TEST_VALGRIND "Also run the scenario under valgrind" ${_valgrind_default})
set(MOIRAI_VALGRIND_SUPPRESSIONS ${CMAKE_CURRENT_SOURCE_DIR}/valgrind/moirai.supp
    CACHE STRING "Valgrind suppression files (colon separated)")

# moirai_test(<name> <service|spill> <service binary> <check: service|spill|
#             none> <io 1|0> <scenario: activities|direct> <env...>
#             COMMAND <command...>)
function(moirai_test name mode service check io scenario)
    cmake_parse_arguments(T "" "" "COMMAND" ${ARGN})
    set(_work ${CMAKE_CURRENT_BINARY_DIR}/${name})
    add_test(NAME ${name}
             COMMAND bash ${CMAKE_CURRENT_SOURCE_DIR}/run_case.sh ${mode}
                     ${service} ${_work} ${T_COMMAND})
    set_tests_properties(${name} PROPERTIES
        ENVIRONMENT "PYTHONPATH=${MOIRAI_PYTHON_DIR};${T_UNPARSED_ARGUMENTS}"
        TIMEOUT 120)
    add_test(NAME check_${name}
             COMMAND ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/check_provenance.py
                     ${_work} ${check} ${io} ${scenario})
    set_tests_properties(check_${name} PROPERTIES DEPENDS ${name})
endfunction()

foreach(_dbg "" "_dbg")
    add_executable(test_api_c${_dbg} c/test_api.c)
    target_link_libraries(test_api_c${_dbg} PRIVATE moirai${_dbg})
    target_compile_options(test_api_c${_dbg} PRIVATE ${MOIRAI_WARNINGS})
    add_executable(test_api_cpp${_dbg} cpp/test_api.cpp)
    target_link_libraries(test_api_cpp${_dbg} PRIVATE moirai${_dbg})
    target_compile_options(test_api_cpp${_dbg} PRIVATE ${MOIRAI_WARNINGS})

    set(_service $<TARGET_FILE:moirai-service${_dbg}>)
    set(_cmd_c $<TARGET_FILE:test_api_c${_dbg}>)
    set(_cmd_cpp $<TARGET_FILE:test_api_cpp${_dbg}>)
    set(_langs c cpp)
    set(_debug_env)
    if(_dbg)
        set(_debug_env MOIRAI_TEST_DEBUG=1)
    endif()
    if(MOIRAI_BUILD_PYTHON)
        set(_cmd_py ${Python_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/py/test_api.py)
        list(APPEND _langs py)
    endif()

    foreach(_lang IN LISTS _langs)
        set(_cmd ${_cmd_${_lang}})
        set(_t moirai_${_lang}${_dbg})
        # Through moirai-service, with and without I/O tracing.
        moirai_test(${_t}_service service ${_service} service 1 activities
                    MOIRAI_TRACE_IO=1 ${_debug_env} COMMAND ${_cmd})
        moirai_test(${_t}_service_noio service ${_service} service 0 activities
                    MOIRAI_TRACE_IO=0 ${_debug_env} COMMAND ${_cmd})
        # No service: everything in the spill file.
        moirai_test(${_t}_spill spill ${_service} spill 1 activities
                    MOIRAI_TRACE_IO=1 ${_debug_env} COMMAND ${_cmd})
        # A dftracer setting under its moirai name: aggregation on, and the
        # activities are still traced in full.
        moirai_test(${_t}_aggregation service ${_service} service 1 activities
                    MOIRAI_TRACE_IO=1 MOIRAI_ENABLE_AGGREGATION=1 ${_debug_env}
                    COMMAND ${_cmd})
        # Entities and their relations declared directly, no activities.
        moirai_test(${_t}_direct service ${_service} service 0 direct
                    MOIRAI_TRACE_IO=1 ${_debug_env} COMMAND ${_cmd} direct)
        # Tracing off: no trace, and the API still works.
        moirai_test(${_t}_disabled spill ${_service} none 1 activities
                    MOIRAI_ENABLE=0 ${_debug_env} COMMAND ${_cmd})
        # The full scenario under valgrind's memcheck: no memory error and
        # no leak in the application, and the same provenance.
        if(MOIRAI_TEST_VALGRIND)
            if(_lang STREQUAL "py")
                set(_vg py)
            else()
                set(_vg c)
            endif()
            moirai_test(${_t}_valgrind service ${_service} service 1 activities
                        MOIRAI_TRACE_IO=1 MOIRAI_TEST_VALGRIND=${_vg}
                        MOIRAI_TEST_SUPPRESSIONS=${MOIRAI_VALGRIND_SUPPRESSIONS}
                        MOIRAI_BIND_SIGNALS=0 ${_debug_env} COMMAND ${_cmd})
            set_tests_properties(${_t}_valgrind check_${_t}_valgrind
                                 PROPERTIES LABELS valgrind)
            set_tests_properties(${_t}_valgrind PROPERTIES TIMEOUT 900)
        endif()
    endforeach()
endforeach()
