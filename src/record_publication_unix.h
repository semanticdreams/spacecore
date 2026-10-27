#pragma once

// Native-only private entry. PE must use the Wine dispatch ABI, never this symbol.
#if !defined(__linux__) || !defined(__x86_64__) || defined(_WIN32)
#error "record publication Unix adapter requires native Linux x86_64"
#endif

#include "record_publication_wine_abi.h"

extern "C" int32_t srp_unix_call(SrpCall* call) noexcept;
