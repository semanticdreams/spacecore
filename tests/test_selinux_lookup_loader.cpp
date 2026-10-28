#include <dlfcn.h>
#include <iostream>

int main(int argc, char** argv)
{
    if (argc < 2) return 2;
    void* system = nullptr;
    if (argc > 2) {
        system = dlopen("libselinux.so.1", RTLD_NOW | RTLD_GLOBAL);
        if (!system) { std::cerr << dlerror() << '\n'; return 1; }
    }
    void* consumer = dlopen(argv[1], RTLD_NOW | RTLD_GLOBAL);
    if (!consumer) { std::cerr << dlerror() << '\n'; return 1; }
    auto run = reinterpret_cast<int(*)(int)>(dlsym(consumer, "space_selinux_lookup_probe"));
    if (!run) { std::cerr << "missing shared probe\n"; dlclose(consumer); return 1; }
    const int result = run(argc > 2);
    dlclose(consumer);
    if (system) dlclose(system);
    return result;
}
