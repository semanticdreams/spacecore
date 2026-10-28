// Exercise the actual standalone-host source without the CMake capability.
#undef SPACE_RECORD_PUBLICATION_SELINUX
#include "../src/record_publication.cpp"
#include <fstream>
#include <iostream>

int main()
{
    namespace filesystem = std::filesystem;
    const auto root = filesystem::temp_directory_path() / ("publication-no-selinux-" +
        std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    filesystem::create_directory(root);
    try {
        if (::setxattr(root.c_str(), "user.unsupported", "x", 1, 0) != 0)
            throw std::runtime_error("unsupported-metadata fixture failed");
        bool refused = false;
        try { record_publication::publish(root / "record", "secret"); }
        catch (const std::exception& error) {
            refused = std::string(error.what()).find("unsupported") != std::string::npos;
        }
        if (!refused || filesystem::exists(root / "record") || filesystem::exists(root / ".space-publication"))
            throw std::runtime_error("capability-absent host must refuse before namespace/payload");
        filesystem::remove_all(root);
        return 0;
    } catch (const std::exception& error) {
        filesystem::remove_all(root);
        std::cerr << error.what() << '\n';
        return 1;
    }
}
