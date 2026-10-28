#pragma once

#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace record_publication::selinux {

// Raw counted security.selinux bytes, including the single final NUL. Absence
// is distinct from unreadable/unsupported metadata, which throws.
using Label = std::optional<std::string>;
Label inspect(int fd);
// Successful validation is allocation-free, including emergency cleanup paths.
void validate_metadata(int fd, const Label* expected = nullptr);
void require_equal(const Label& actual, const Label& expected);

struct DefaultContext {
    Label fixed;
    std::string digest;
    std::vector<std::string> files;
    bool operator==(const DefaultContext& other) const;
};
// Optional spec path is an internal fixture seam, never a publication option.
DefaultContext default_context(const std::filesystem::path& destination,
                               const std::filesystem::path& specs = {});
bool supported_mount_options(const std::string& filesystem, const std::string& mount_options,
                             const std::string& super_options);

class NewLabelAuthority {
public:
    // Borrows parent_fd; its Attempt must retain it throughout this lifetime.
    NewLabelAuthority(int parent_fd, const std::filesystem::path& canonical_destination,
                      const std::filesystem::path& specs = {});
    void validate(int stage_fd) const;
private:
    struct State {
        DefaultContext defaults;
        std::string expected, task, mount;
        int policy = 0, enforcing = 0;
        bool operator==(const State& other) const;
    };
    State read() const;
    int parent_fd_;
    std::filesystem::path destination_, specs_;
    Label parent_label_;
    unsigned long long parent_device_, parent_inode_;
    State baseline_;
};
} // namespace record_publication::selinux
