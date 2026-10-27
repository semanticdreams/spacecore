#pragma once

#include "record_publication_wine_abi.h"

#include <algorithm>
#include <array>
#include <stdexcept>
#include <string_view>

namespace record_publication::wine::detail {

struct Binding {
    std::array<uint8_t, 32> build_id;
    uint64_t module_device, module_inode;
};

inline Binding parse_binding(std::string_view input)
{
    const auto invalid = [] { throw std::runtime_error("record publication: invalid Wine publication binding"); };
    if (input.size() < 68 || input.size() > 106 || input[64] != ':') invalid();
    Binding binding {};
    for (size_t i = 0; i < 64; ++i) {
        const char c = input[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) invalid();
        binding.build_id[i / 2] |= static_cast<uint8_t>((c <= '9' ? c - '0' : c - 'a' + 10) << (i % 2 ? 0 : 4));
    }
    const auto separator = input.find(':', 65);
    if (separator == std::string_view::npos) invalid();
    const auto decimal = [&](std::string_view text) {
        if (text.empty() || (text.size() > 1 && text.front() == '0')) invalid();
        uint64_t value = 0;
        for (const char c : text) {
            if (c < '0' || c > '9' || value > (UINT64_MAX - (c - '0')) / 10) invalid();
            value = value * 10 + (c - '0');
        }
        return value;
    };
    binding.module_device = decimal(input.substr(65, separator - 65));
    binding.module_inode = decimal(input.substr(separator + 1));
    if (!binding.module_inode) invalid();
    return binding;
}

inline void validate_identity(const SrpIdentity& identity, const Binding& binding, uint64_t challenge)
{
    if (identity.size != sizeof(SrpIdentity) || identity.abi != SRP_ABI
        || identity.challenge != challenge || identity.echo != challenge
        || !std::equal(binding.build_id.begin(), binding.build_id.end(), identity.pe_build_id)
        || !std::equal(binding.build_id.begin(), binding.build_id.end(), identity.unix_build_id)
        || identity.module_device != binding.module_device || identity.module_inode != binding.module_inode
        || identity.architecture != SRP_ARCH_X86_64 || identity.features != SRP_REQUIRED_FEATURES) {
        throw std::runtime_error("record publication: Wine publication identity mismatch");
    }
}

} // namespace record_publication::wine::detail
