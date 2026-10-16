#pragma once

#include <filesystem>
#include <functional>
#include <optional>
#include <string>
#include <string_view>

namespace record_publication {

using Stage = std::function<void(const std::filesystem::path&)>;

struct Hooks {
    std::function<void()> before_security, before_commit, before_cleanup;
};

struct Result {
    bool committed = false;
    std::optional<std::string> cleanup_error;
};

Result publish(const std::filesystem::path& destination,
               std::string_view expected_bytes, const Stage& stage,
               const Hooks& hooks = {});

} // namespace record_publication
