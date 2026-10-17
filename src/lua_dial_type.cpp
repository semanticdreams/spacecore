#include <sol/sol.hpp>

#include "dial_type.h"
#include "input_dial_type.h"

namespace {

sol::table to_lua_array(sol::state_view lua, const std::vector<int>& values)
{
    sol::table out = lua.create_table();
    for (size_t i = 0; i < values.size(); ++i) {
        out[static_cast<int>(i + 1)] = values[i];
    }
    return out;
}

sol::object dial_type_poll(DialType& dial, sol::this_state state)
{
    sol::state_view lua(state);
    std::optional<DialTypePendingInput> pending = dial.poll();
    if (!pending.has_value()) {
        return sol::make_object(lua, sol::nil);
    }

    sol::table out = lua.create_table();
    out[1] = to_lua_array(lua, pending->left);
    out[2] = to_lua_array(lua, pending->right);
    return sol::make_object(lua, out);
}

sol::object dial_pending_to_lua(const std::optional<DialTypePendingInput>& pending, sol::this_state state)
{
    sol::state_view lua(state);
    if (!pending.has_value()) {
        return sol::make_object(lua, sol::nil);
    }
    sol::table out = lua.create_table();
    out[1] = to_lua_array(lua, pending->left);
    out[2] = to_lua_array(lua, pending->right);
    return sol::make_object(lua, out);
}

sol::object input_dial_type_poll_primary(InputDialType& dial, sol::this_state state)
{
    return dial_pending_to_lua(dial.poll_primary(), state);
}

sol::object input_dial_type_poll_gamepad(InputDialType& dial, int instanceId, sol::this_state state)
{
    return dial_pending_to_lua(dial.poll_gamepad(static_cast<SDL_JoystickID>(instanceId)), state);
}

sol::table input_dial_type_gamepad_ids(InputDialType& dial, sol::this_state state)
{
    sol::state_view lua(state);
    sol::table out = lua.create_table();
    const std::vector<SDL_JoystickID> ids = dial.gamepad_ids();
    for (size_t i = 0; i < ids.size(); ++i) {
        out[static_cast<int>(i + 1)] = ids[i];
    }
    return out;
}

sol::table stick_dump_to_lua(sol::state_view lua, const DialTypeStickDump& dump)
{
    sol::table out = lua.create_table();
    sol::table position = lua.create_table();
    position[1] = dump.positionX;
    position[2] = dump.positionY;
    out["position"] = position;
    out["angle"] = dump.angle;
    out["active"] = dump.active;
    out["dialing"] = dump.dialing;
    return out;
}

sol::table dial_type_dump(DialType& dial, sol::this_state state)
{
    sol::state_view lua(state);
    const DialTypeDump dump = dial.dump();
    sol::table out = lua.create_table();
    sol::table sticks = lua.create_table();
    sticks[1] = stick_dump_to_lua(lua, dump.left);
    sticks[2] = stick_dump_to_lua(lua, dump.right);
    out["sticks"] = sticks;
    out["has-input"] = dump.hasInput;
    if (dump.pending.has_value()) {
        sol::table pending = lua.create_table();
        pending[1] = to_lua_array(lua, dump.pending->left);
        pending[2] = to_lua_array(lua, dump.pending->right);
        out["pending"] = pending;
    }
    return out;
}

sol::table create_dial_type_table(sol::state_view lua)
{
    sol::table dial_type_table = lua.create_table();
    dial_type_table.new_usertype<DialType>(
        "DialType",
        sol::constructors<DialType()>(),
        "update", &DialType::update,
        "poll", &dial_type_poll,
        "has-input", &DialType::has_input,
        "dump", &dial_type_dump,
        "reset", &DialType::reset);

    dial_type_table.new_usertype<InputDialType>(
        "InputDialType",
        sol::constructors<InputDialType(InputState&)>(),
        "update", &InputDialType::update,
        "update-primary", &InputDialType::update_primary,
        "update-gamepad", [](InputDialType& dial, int instanceId) {
            return dial.update_gamepad(static_cast<SDL_JoystickID>(instanceId));
        },
        "has-input", &InputDialType::has_input,
        "has-input-for", [](InputDialType& dial, int instanceId) {
            return dial.has_input_for(static_cast<SDL_JoystickID>(instanceId));
        },
        "poll-primary", &input_dial_type_poll_primary,
        "poll-gamepad", &input_dial_type_poll_gamepad,
        "gamepad-ids", &input_dial_type_gamepad_ids,
        "reset", &InputDialType::reset);

    dial_type_table.set_function("DialType", []() {
        return DialType();
    });
    dial_type_table.set_function("InputDialType", [](sol::optional<sol::object> inputStateObject) {
        constexpr const char* error = "InputDialType requires a non-null InputState userdata";
        if (!inputStateObject || !inputStateObject->valid()
            || inputStateObject->get_type() != sol::type::userdata) {
            throw sol::error(error);
        }
        // sol2 accepts userdata without a metatable as any native type.
        lua_State* state = inputStateObject->lua_state();
        inputStateObject->push();
        const bool hasMetatable = lua_getmetatable(state, -1) != 0;
        lua_pop(state, hasMetatable ? 2 : 1);
        if (!hasMetatable || !inputStateObject->is<InputState>()) {
            throw sol::error(error);
        }
        InputState* inputState = inputStateObject->as<InputState*>();
        if (!inputState) {
            throw sol::error(error);
        }
        return InputDialType(*inputState);
    });

    return dial_type_table;
}

} // namespace

void lua_bind_dial_type(sol::state& lua)
{
    sol::table package = lua["package"];
    sol::table preload = package["preload"];

    preload.set_function("dial-type", [](sol::this_state state) {
        sol::state_view lua(state);
        return create_dial_type_table(lua);
    });
}
