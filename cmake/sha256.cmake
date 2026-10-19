# One existing Trezor implementation supplies SHA-256 and its memzero dependency.
include_guard(GLOBAL)
include(TestBigEndian)
test_big_endian(SPACE_SHA256_BIG_ENDIAN)
if(SPACE_SHA256_BIG_ENDIAN)
    set(_space_sha256_byte_order 4321)
else()
    set(_space_sha256_byte_order 1234)
endif()
get_filename_component(_space_sha256_vendor
    "${CMAKE_CURRENT_LIST_DIR}/../external/wallet-core/trezor-crypto" ABSOLUTE)

if(TARGET TrezorCrypto)
    add_library(space_sha256_backend INTERFACE)
    target_link_libraries(space_sha256_backend INTERFACE TrezorCrypto)
    set(_space_sha256_provider TrezorCrypto)
else()
    add_library(space_sha256_backend STATIC
        "${_space_sha256_vendor}/crypto/sha2.c"
        "${_space_sha256_vendor}/crypto/memzero.c")
    target_include_directories(space_sha256_backend PUBLIC "${_space_sha256_vendor}/include")
    set(_space_sha256_provider space_sha256_backend)
endif()

# sha2.h otherwise silently defaults to little endian. Do not leak these macros
# to engine or binding consumers (nor alter global directory definitions).
target_compile_definitions(${_space_sha256_provider} PRIVATE
    LITTLE_ENDIAN=1234 BIG_ENDIAN=4321 BYTE_ORDER=${_space_sha256_byte_order})
