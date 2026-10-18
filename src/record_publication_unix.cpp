#include "record_publication_unix.h"
#include "record_publication_operation.h"

#include <algorithm>
#include <array>
#include <cstring>
#include <exception>
#include <limits>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <string_view>

namespace {
using record_publication::detail::Operation;
using record_publication::detail::Phase;
using record_publication::detail::Reply;

static_assert(sizeof(uintptr_t) == sizeof(uint64_t));
static_assert(static_cast<uint32_t>(Phase::start) == SRP_START
    && static_cast<uint32_t>(Phase::before_write) == SRP_BEFORE_WRITE
    && static_cast<uint32_t>(Phase::before_security) == SRP_BEFORE_SECURITY
    && static_cast<uint32_t>(Phase::before_commit) == SRP_BEFORE_COMMIT
    && static_cast<uint32_t>(Phase::before_cleanup) == SRP_BEFORE_CLEANUP
    && static_cast<uint32_t>(Phase::done) == SRP_DONE);

std::string_view view(SrpSlice slice) noexcept
{
    return slice.size ? std::string_view(reinterpret_cast<const char*>(slice.address), slice.size) : std::string_view();
}

struct Context {
    Context(std::string_view path, std::string_view payload)
        : operation(std::filesystem::path(path), payload) {}

    void poison(const char* error) noexcept
    {
        if (poisoned) return; // Retain the first contained error, including an empty diagnostic.
        poisoned = true;
        const std::string_view text(error);
        constexpr std::string_view marker = "[truncated]";
        transport_size = std::min(text.size(), transport.size());
        transport_truncated = text.size() > transport.size();
        const auto prefix = transport_truncated ? transport.size() - marker.size() : transport_size;
        if (prefix) std::memcpy(transport.data(), text.data(), prefix);
        if (transport_truncated) std::memcpy(transport.data() + prefix, marker.data(), marker.size());
    }

    Operation operation;
    std::mutex mutex;
    uint64_t id = 0, sequence = 0;
    bool retired = false, poisoned = false, transport_truncated = false;
    std::array<char, 512> transport {};
    size_t transport_size = 0;
};

std::mutex registry_mutex;
std::map<uint64_t, std::shared_ptr<Context>> registry;
uint64_t next_id = 1; // 0 is the exhausted sentinel; no ID is recycled, even after failed insertion.

std::shared_ptr<Context> find_context(uint64_t id)
{
    std::lock_guard<std::mutex> lock(registry_mutex);
    const auto found = registry.find(id);
    return found == registry.end() ? nullptr : found->second;
} // Registry lock is released before acquiring a context lock or doing native work.

void register_context(const std::shared_ptr<Context>& context)
{
    std::lock_guard<std::mutex> lock(registry_mutex);
    if (!next_id) throw std::overflow_error("publication context IDs exhausted");
    context->id = next_id;
    next_id = next_id == UINT64_MAX ? 0 : next_id + 1;
    registry.emplace(context->id, context);
}

struct Range { uint64_t address, size; };

bool valid_range(Range range) noexcept
{
    if (!range.size) return range.address == 0;
    return range.address != 0 && range.size <= static_cast<uint64_t>(PTRDIFF_MAX)
        && range.size <= UINTPTR_MAX - range.address;
}

bool overlaps(Range left, Range right) noexcept
{
    return left.size && right.size && left.address < right.address + right.size
        && right.address < left.address + left.size;
}

// Validate integer ranges before reading any slice. Memory itself is caller-owned
// valid synchronous storage; this is not a hostile pointer probing boundary.
const char* validate(const SrpCall& request, const SrpCall* frame, bool& copy_outputs) noexcept
{
    const std::array<Range, 3> inputs {{{request.path.address, request.path.size},
        {request.payload.address, request.payload.size}, {request.hook_error.address, request.hook_error.size}}};
    const std::array<Range, 3> outputs {{{request.primary_error.address, request.primary_error.capacity},
        {request.cleanup_error.address, request.cleanup_error.capacity},
        {request.transport_error.address, request.transport_error.capacity}}};
    const Range header {reinterpret_cast<uintptr_t>(frame), sizeof(*frame)};
    for (auto output : outputs) {
        if (!valid_range(output) || overlaps(output, header)) {
            copy_outputs = false;
            return "invalid output buffer range";
        }
    }
    for (size_t i = 0; i < outputs.size(); ++i) {
        for (size_t j = i + 1; j < outputs.size(); ++j) {
            if (overlaps(outputs[i], outputs[j])) {
                copy_outputs = false;
                return "overlapping output buffers";
            }
        }
    }
    for (auto input : inputs) {
        if (!valid_range(input) || overlaps(input, header)) return "invalid input slice range";
        for (auto output : outputs) {
            if (overlaps(input, output)) {
                copy_outputs = false;
                return "overlapping input and output storage";
            }
        }
    }
    if (request.reserved) return "reserved must be zero";
    if (request.opcode < SRP_BEGIN || request.opcode > SRP_RELEASE) return "invalid opcode";
    if (request.opcode != SRP_BEGIN && (request.path.size || request.payload.size)) return "unused path/payload must be zero";
    if (request.opcode == SRP_ADVANCE) {
        if (request.reply != SRP_CONTINUE && request.reply != SRP_FAILED) return "invalid hook reply";
        if (request.reply == SRP_CONTINUE && request.hook_error.size) return "successful reply has an error slice";
    } else {
        if (request.reply != SRP_CONTINUE) return "opcode requires CONTINUE";
        if (request.opcode != SRP_CANCEL && request.hook_error.size) return "unused hook error must be zero";
    }
    if (request.opcode == SRP_BEGIN) {
        if (request.context || request.sequence || request.event != SRP_START) return "BEGIN requires context0/START/sequence0";
        const auto path = view(request.path);
        if (path.empty() || path.front() != '/' || path.find('\0') != std::string_view::npos)
            return "BEGIN requires a nonempty absolute NUL-free host path";
    }
    return nullptr;
}

void prepare_text(SrpCall& response, SrpBuffer& output, std::string_view text, uint32_t truncated,
                  bool copy_outputs) noexcept
{
    output.required = text.size();
    const auto count = copy_outputs ? std::min<uint64_t>(text.size(), output.capacity) : 0;
    if (text.size() > count) response.flags |= truncated;
}

void copy_text(const SrpBuffer& output, std::string_view text, bool copy_outputs) noexcept
{
    const auto count = copy_outputs ? std::min<uint64_t>(text.size(), output.capacity) : 0;
    if (count) std::memcpy(reinterpret_cast<void*>(output.address), text.data(), count);
}

// Scalar truth and presence are published before any diagnostic byte copy.
void respond(SrpCall& response, const Context* context, const char* transient_error,
             bool copy_outputs) noexcept
{
    response.path = response.payload = response.hook_error = {};
    response.reply = SRP_CONTINUE;
    response.reserved = 0;
    response.context = context ? context->id : 0;
    response.sequence = context ? context->sequence : 0;
    response.event = context ? static_cast<uint32_t>(context->operation.state().phase) : SRP_START;
    response.flags = context ? SRP_VALID : 0;
    response.primary_state = SRP_PRIMARY_ABSENT;
    std::string_view primary, cleanup, transport;
    if (context) {
        const auto& state = context->operation.state();
        if (state.committed) response.flags |= SRP_COMMITTED;
        if (state.phase == Phase::done) response.flags |= SRP_DONE_FLAG;
        if (state.failure) { response.primary_state = SRP_PRIMARY_PRESENT; primary = *state.failure; }
        if (state.cleanup_error) { response.flags |= SRP_CLEANUP_PRESENT; cleanup = *state.cleanup_error; }
        if (context->poisoned) response.flags |= SRP_POISONED;
        transport = {context->transport.data(), context->transport_size};
        if (context->transport_truncated && !transient_error) response.flags |= SRP_TRANSPORT_TRUNCATED;
    }
    if (transient_error) transport = transient_error;
    // Required counts are output-only, including on validation responses.
    prepare_text(response, response.primary_error, primary, SRP_PRIMARY_TRUNCATED, copy_outputs);
    prepare_text(response, response.cleanup_error, cleanup, SRP_CLEANUP_TRUNCATED, copy_outputs);
    prepare_text(response, response.transport_error, transport, SRP_TRANSPORT_TRUNCATED, copy_outputs);
    copy_text(response.primary_error, primary, copy_outputs);
    copy_text(response.cleanup_error, cleanup, copy_outputs);
    copy_text(response.transport_error, transport, copy_outputs);
}

int32_t invoke_context(SrpCall& response, const SrpCall& request, Context& context,
                       const char* invalid, bool copy_outputs) noexcept
{
    if (context.retired) {
        respond(response, nullptr, "retired context", copy_outputs);
        return SRP_INVALID_ARGUMENT;
    }
    if (!invalid && request.opcode != SRP_SNAPSHOT) {
        if (request.opcode == SRP_BEGIN || request.sequence != context.sequence
            || request.event != static_cast<uint32_t>(context.operation.state().phase))
            invalid = "stale or incompatible continuation";
        else if (request.opcode == SRP_ADVANCE && context.operation.state().phase == Phase::done)
            invalid = "DONE accepts no advance";
        else if (context.sequence == UINT64_MAX) invalid = "operation sequence exhausted";
    }
    if (invalid) {
        respond(response, &context, invalid, copy_outputs);
        return SRP_INVALID_ARGUMENT;
    }
    if (request.opcode == SRP_SNAPSHOT) {
        respond(response, &context, nullptr, copy_outputs);
        return SRP_SUCCESS;
    }
    if (context.poisoned && request.opcode == SRP_ADVANCE && context.operation.state().phase != Phase::before_cleanup) {
        respond(response, &context, nullptr, copy_outputs);
        return SRP_UNSUCCESSFUL;
    }
    ++context.sequence; // Accepted logical transition is consumed even if invocation throws.
    try {
        switch (request.opcode) {
        case SRP_ADVANCE:
            context.operation.advance(Reply {static_cast<Phase>(request.event), request.reply == SRP_FAILED,
                std::string(view(request.hook_error))});
            break;
        case SRP_CANCEL:
            context.operation.cancel(view(request.hook_error));
            break;
        case SRP_RELEASE: {
            auto phase = context.operation.state().phase;
            if (phase != Phase::done && phase != Phase::before_cleanup) phase = context.operation.cancel({});
            if (phase == Phase::before_cleanup) phase = context.operation.advance({Phase::before_cleanup, false, {}});
            if (phase != Phase::done) throw std::runtime_error("release finalization incomplete");
            // Native DONE with cleanup_error is still completed finalization. Copy
            // its error-bearing result before retiring, not a false clean success.
            std::lock_guard<std::mutex> lock(registry_mutex);
            respond(response, &context, nullptr, copy_outputs);
            context.retired = true;
            registry.erase(context.id);
            return SRP_SUCCESS;
        }
        default:
            throw std::logic_error("invalid accepted opcode");
        }
    } catch (const std::exception& error) {
        context.poison(error.what());
        respond(response, &context, nullptr, copy_outputs);
        return SRP_UNSUCCESSFUL;
    } catch (...) {
        context.poison("unknown native adapter exception");
        respond(response, &context, nullptr, copy_outputs);
        return SRP_UNSUCCESSFUL;
    }
    respond(response, &context, nullptr, copy_outputs);
    return SRP_SUCCESS;
}
} // namespace

extern "C" int32_t srp_unix_call(SrpCall* call) noexcept
{
    if (!call || call->size != sizeof(SrpCall) || call->abi != SRP_ABI) return SRP_INVALID_ARGUMENT;
    const SrpCall request = *call; // Capture before clearing any caller-owned input fields.
    bool copy_outputs = true;
    const char* invalid = validate(request, call, copy_outputs);
    try {
        if (request.context) {
            auto context = find_context(request.context);
            if (context) {
                std::lock_guard<std::mutex> lock(context->mutex);
                // The shared owner may predate RELEASE. Recheck retirement under
                // the same context lock before reading state or touching native work.
                return invoke_context(*call, request, *context, invalid, copy_outputs);
            }
        }
        if (invalid || request.opcode != SRP_BEGIN) {
            respond(*call, nullptr, invalid ? invalid : "unknown context", copy_outputs);
            return SRP_INVALID_ARGUMENT;
        }
        auto context = std::make_shared<Context>(view(request.path), view(request.payload));
        std::lock_guard<std::mutex> lock(context->mutex);
        register_context(context);
        respond(*call, context.get(), nullptr, copy_outputs);
        return SRP_SUCCESS;
    } catch (const std::exception& error) {
        respond(*call, nullptr, error.what(), copy_outputs);
        return SRP_UNSUCCESSFUL;
    } catch (...) {
        respond(*call, nullptr, "unknown native adapter exception", copy_outputs);
        return SRP_UNSUCCESSFUL;
    }
}
