# The system backend conflates regex failure with negative lookup. Publication
# must use this pinned private archive, never an unpatched system fallback.
include(FetchContent)
if(POLICY CMP0135)
    cmake_policy(SET CMP0135 NEW)
endif()
FetchContent_Declare(space_selinux_source
    URL https://github.com/SELinuxProject/selinux/releases/download/3.9/libselinux-3.9.tar.gz
    URL_HASH SHA256=e7ee2c01dba64a0c35c9d7c9c0e06209d8186b325b0638a0d83f915cc3c101e8
)
FetchContent_MakeAvailable(space_selinux_source)
set(_space_selinux_patch "${CMAKE_CURRENT_LIST_DIR}/patch-private-selinux.py")
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_space_selinux_patch}")
execute_process(COMMAND "${Python3_EXECUTABLE}" "${_space_selinux_patch}"
    "${space_selinux_source_SOURCE_DIR}" RESULT_VARIABLE _space_selinux_patch_result)
if(NOT _space_selinux_patch_result EQUAL 0)
    message(FATAL_ERROR "Private SELinux source verification/patch failed")
endif()

find_program(SPACE_SELINUX_MAKE NAMES gmake make REQUIRED)
find_package(Threads REQUIRED)
pkg_check_modules(SPACE_PCRE2 REQUIRED IMPORTED_TARGET libpcre2-8)
pkg_check_modules(SPACE_SEPOL REQUIRED IMPORTED_TARGET libsepol)
string(JOIN " " _space_pcre_flags ${SPACE_PCRE2_CFLAGS})
set(_space_selinux_archive "${space_selinux_source_BINARY_DIR}/libspace_selinux.a")
file(MAKE_DIRECTORY "${space_selinux_source_BINARY_DIR}")
set(_space_selinux_flags "${space_selinux_source_BINARY_DIR}/build-flags.txt")
file(GENERATE OUTPUT "${_space_selinux_flags}" CONTENT
    "CC=${CMAKE_C_COMPILER}\nAR=${CMAKE_AR}\nRANLIB=${CMAKE_RANLIB}\nCFLAGS=-O2 -fPIC -fvisibility=hidden\nPCRE=${_space_pcre_flags};${SPACE_PCRE2_VERSION}\nDISABLE_SETRANS;NO_X_BACKEND;NO_ANDROID_BACKEND\n")
file(GLOB _space_selinux_sources CONFIGURE_DEPENDS
    "${space_selinux_source_SOURCE_DIR}/src/*.c"
    "${space_selinux_source_SOURCE_DIR}/src/*.h"
    "${space_selinux_source_SOURCE_DIR}/include/selinux/*.h")

# No parent all/install/relabel/shared/bindings target is invoked. The regular
# upstream archive source filter excludes SWIG/audit2why/Android-only backends.
add_custom_command(OUTPUT "${_space_selinux_archive}"
    COMMAND "${SPACE_SELINUX_MAKE}" -B -C "${space_selinux_source_SOURCE_DIR}/src"
        "${_space_selinux_archive}" "LIBA=${_space_selinux_archive}"
        "CC=${CMAKE_C_COMPILER}" "AR=${CMAKE_AR}" "RANLIB=${CMAKE_RANLIB}"
        "CFLAGS=-O2 -fPIC -fvisibility=hidden"
        "PCRE_CFLAGS=-DUSE_PCRE2 -DPCRE2_CODE_UNIT_WIDTH=8 ${_space_pcre_flags}"
        "DISABLE_FLAGS=-DDISABLE_SETRANS -DNO_X_BACKEND -DNO_ANDROID_BACKEND"
        "DISABLE_X11=y" "LABEL_BACKEND_ANDROID=n"
    COMMAND "${CMAKE_COMMAND}" -E touch "${_space_selinux_archive}"
    DEPENDS ${_space_selinux_sources} "${CMAKE_CURRENT_LIST_FILE}" "${_space_selinux_patch}" "${_space_selinux_flags}"
    VERBATIM)
add_custom_target(space_selinux_archive DEPENDS "${_space_selinux_archive}")
add_library(space_private_selinux STATIC IMPORTED GLOBAL)
set_target_properties(space_private_selinux PROPERTIES
    IMPORTED_LOCATION "${_space_selinux_archive}"
    INTERFACE_INCLUDE_DIRECTORIES "${space_selinux_source_SOURCE_DIR}/include"
    INTERFACE_LINK_LIBRARIES "PkgConfig::SPACE_PCRE2;PkgConfig::SPACE_SEPOL;Threads::Threads;${CMAKE_DL_LIBS}"
    INTERFACE_LINK_OPTIONS "-Wl,--exclude-libs,libspace_selinux.a")
add_dependencies(space_private_selinux space_selinux_archive)

add_library(space_record_selinux STATIC "${PROJECT_SOURCE_DIR}/src/record_publication_selinux.cpp")
set_target_properties(space_record_selinux PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_compile_definitions(space_record_selinux PRIVATE SPACE_RECORD_PUBLICATION_SELINUX=1)
target_link_libraries(space_record_selinux PRIVATE space_private_selinux)
# Limit the capability define to the core translation unit, avoiding accidental
# enablement in separately compiled/unsupported Wine host helpers.
set_source_files_properties("${PROJECT_SOURCE_DIR}/src/record_publication.cpp"
    PROPERTIES COMPILE_DEFINITIONS SPACE_RECORD_PUBLICATION_SELINUX=1)
