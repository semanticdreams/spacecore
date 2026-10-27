#include "lua_sha256.h"

#include <string>

#include <TrezorCrypto/sha2.h>

void lua_bind_sha256(sol::state& lua)
{
    sol::table preload = lua["package"]["preload"];
    preload.set_function("sha256", [](sol::this_state state) {
        sol::state_view lua_view(state);
        sol::table module = lua_view.create_table();
        module.set_function("hash", [](sol::object content) {
            if (content.get_type() != sol::type::string)
            {
                throw sol::error("sha256.hash requires a string");
            }
            const auto bytes = content.as<sol::string_view>();
            char digest[SHA256_DIGEST_STRING_LENGTH];
            sha256_Data(reinterpret_cast<const uint8_t*>(bytes.data()), bytes.size(), digest);
            return std::string(digest, SHA256_DIGEST_STRING_LENGTH - 1);
        });
        return module;
    });
}
