#pragma once

#include <filesystem>
#include <functional>
#include <optional>
#include <string>
#include <string_view>

namespace record_publication {

struct Hooks {
    std::function<void()> before_write, before_security, before_commit, before_cleanup;
};

struct Result {
    bool committed = false;
    std::optional<std::string> cleanup_error;
};

Result publish(const std::filesystem::path& destination,
               std::string_view payload, const Hooks& hooks = {});

} // namespace record_publication
