#include <cstdlib>
#include <exception>
#include <iostream>
#include <stdexcept>

#include <sol/sol.hpp>
#include <TrezorCrypto/memzero.h>

#include "lua_sha256.h"

int main()
{
    try
    {
        unsigned char wiped[] = {1, 2, 3};
        memzero(wiped, sizeof(wiped));
        for (unsigned char byte : wiped)
        {
            if (byte != 0)
            {
                throw std::runtime_error("memzero provider failed");
            }
        }
        sol::state lua;
        lua.open_libraries(sol::lib::base, sol::lib::package, sol::lib::string);
        // Keep expected type errors quiet, as the application runtime does.
        lua.set_exception_handler([](lua_State* state,
                                     sol::optional<const std::exception&>,
                                     sol::string_view what) {
            lua_pushlstring(state, what.data(), what.size());
            return 1;
        });
        lua_bind_sha256(lua);
        int userdata = 0;
        lua["test_userdata"] = &userdata;
        lua.script(R"(
            assert(type(package.preload.sha256) == "function", "native SHA preload missing")
            local sha = require("sha256")
            local bytes = ""
            for i = 0, 255 do bytes = bytes .. string.char(i) end
            local vectors = {
                {"", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"},
                {"abc", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"},
                {string.char(0), "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"},
                {"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"},
                {bytes, "40aff2e9d2d8922e47afd4648e6967497158785fbd1da870e7110266bf944880"}
            }
            for _, vector in ipairs(vectors) do
                local digest = sha.hash(vector[1])
                assert(digest == vector[2], "SHA vector mismatch")
                assert(#digest == 64 and digest:match("^[0-9a-f]+$"), "noncanonical digest")
            end
            local function rejected(...)
                local ok, err = pcall(sha.hash, ...)
                assert(not ok and type(err) == "string", "non-string input accepted")
            end
            rejected()
            rejected(nil)
            rejected(123)
            rejected(false)
            rejected({})
            rejected(test_userdata)
        )");
        std::cout << "SHA-256: 5 exact vectors and 6 strict input rejections passed\n";
        return EXIT_SUCCESS;
    }
    catch (const std::exception& error)
    {
        std::cerr << error.what() << '\n';
        return EXIT_FAILURE;
    }
}
