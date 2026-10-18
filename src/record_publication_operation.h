#pragma once

#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <string_view>

namespace record_publication::detail {

enum class Phase {
    start = 0,
    before_write = 1,
    before_security = 2,
    before_commit = 3,
    before_cleanup = 4,
    done = 5
};

struct Reply {
    Phase phase;
    bool failed;
    std::string error;
};

struct State {
    Phase phase = Phase::start;
    bool committed = false;
    std::optional<std::string> failure, cleanup_error;
};

// Private per-publication continuation. No callbacks or platform objects escape it.
class Operation {
public:
    Operation(const std::filesystem::path& destination, std::string_view payload);
    ~Operation();
    Operation(const Operation&) = delete;
    Operation& operator=(const Operation&) = delete;

    // Only a reply to the exact pending phase is accepted; done accepts no reply.
    Phase advance(const Reply& reply);
    // Stops publication, yielding cleanup if owned. Cancelling pending cleanup
    // runs it now; cancelling done is a no-op. Postcommit reasons are cleanup errors.
    Phase cancel(std::string_view reason);
    const State& state() const noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

} // namespace record_publication::detail
