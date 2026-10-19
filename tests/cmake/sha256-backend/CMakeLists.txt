cmake_minimum_required(VERSION 3.18)
project(space_sha256_backend_test LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
set(BUILD_SHARED_LIBS OFF CACHE BOOL "Build static libraries" FORCE)
include(CTest)
get_filename_component(SPACE_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
option(SPACE_SHA256_TEST_WALLET_TARGET "Use the real optional wallet crypto target" OFF)
add_subdirectory("${SPACE_ROOT}/external/lua" "${CMAKE_CURRENT_BINARY_DIR}/lua")
if(SPACE_SHA256_TEST_WALLET_TARGET)
    set(TW_TREZOR_TESTS OFF CACHE BOOL "Disable vendor tests" FORCE)
    include(GNUInstallDirs)
    add_subdirectory("${SPACE_ROOT}/external/wallet-core/trezor-crypto"
        "${CMAKE_CURRENT_BINARY_DIR}/trezor-crypto")
endif()
include("${SPACE_ROOT}/cmake/sha256.cmake")

# Fail configuration if either branch starts compiling a duplicate provider.
get_target_property(backend_type space_sha256_backend TYPE)
get_target_property(backend_sources space_sha256_backend SOURCES)
if(SPACE_SHA256_TEST_WALLET_TARGET)
    get_target_property(backend_links space_sha256_backend INTERFACE_LINK_LIBRARIES)
    if(NOT backend_type STREQUAL "INTERFACE_LIBRARY" OR backend_sources
            OR NOT backend_links STREQUAL "TrezorCrypto")
        message(FATAL_ERROR "Wallet branch must exclusively link the real TrezorCrypto target")
    endif()
    get_target_property(provider_sources TrezorCrypto SOURCES)
    foreach(source crypto/sha2.c crypto/memzero.c)
        set(matches "${provider_sources}")
        list(FILTER matches INCLUDE REGEX "^${source}$")
        list(LENGTH matches count)
        if(NOT count EQUAL 1)
            message(FATAL_ERROR "Real provider must compile ${source} exactly once")
        endif()
    endforeach()
    set(provider TrezorCrypto)
else()
    set(expected_sources
        "${SPACE_ROOT}/external/wallet-core/trezor-crypto/crypto/sha2.c"
        "${SPACE_ROOT}/external/wallet-core/trezor-crypto/crypto/memzero.c")
    if(TARGET TrezorCrypto OR NOT backend_type STREQUAL "STATIC_LIBRARY"
            OR NOT backend_sources STREQUAL expected_sources)
        message(FATAL_ERROR "Standalone backend must compile exactly sha2.c and memzero.c")
    endif()
    set(provider space_sha256_backend)
endif()
get_target_property(provider_definitions ${provider} COMPILE_DEFINITIONS)
get_target_property(public_definitions ${provider} INTERFACE_COMPILE_DEFINITIONS)
if(NOT "LITTLE_ENDIAN=1234" IN_LIST provider_definitions
        OR NOT "BIG_ENDIAN=4321" IN_LIST provider_definitions
        OR NOT provider_definitions MATCHES "BYTE_ORDER=(1234|4321)"
        OR public_definitions)
    message(FATAL_ERROR "Provider must have explicit private numeric endian definitions")
endif()
message(STATUS "SHA provider=${provider}; type=${backend_type}; sources=${backend_sources}; definitions=${provider_definitions}")
add_executable(test_lua_sha256_binding
    "${SPACE_ROOT}/tests/test_lua_sha256_binding.cpp"
    "${SPACE_ROOT}/src/lua_sha256.cpp")
target_include_directories(test_lua_sha256_binding PRIVATE "${SPACE_ROOT}/src")
target_include_directories(test_lua_sha256_binding SYSTEM PRIVATE "${SPACE_ROOT}/external/sol2")
target_link_libraries(test_lua_sha256_binding PRIVATE lua space_sha256_backend ${CMAKE_DL_LIBS})
if(UNIX)
    target_link_libraries(test_lua_sha256_binding PRIVATE m)
endif()
add_test(NAME test_lua_sha256_binding COMMAND test_lua_sha256_binding)
