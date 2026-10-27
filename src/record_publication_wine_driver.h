#pragma once

#include "record_publication.h"
#include "record_publication_wine_abi.h"

#include <algorithm>
#include <array>
#include <exception>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace record_publication::wine::detail {

// This consumer owns no loader/module. Its caller must keep Entry and the module
// alive until every synchronous call, including explicit retirement, completes.
struct DriverChannel {
    std::array<char, 4096> initial {};
    std::vector<char> grown;

    char* data() noexcept { return grown.empty() ? initial.data() : grown.data(); }
    size_t capacity() const noexcept { return grown.empty() ? initial.size() : grown.size(); }
    SrpBuffer buffer() noexcept { return {reinterpret_cast<uintptr_t>(data()), capacity(), 0}; }
    bool grow(uint64_t required)
    {
        if (!grown.empty() || required <= capacity()) return false;
        grown.resize(static_cast<size_t>(std::min<uint64_t>(required, 65536)));
        return true;
    }
    std::string text(const SrpBuffer& buffer, bool truncated)
    {
        std::string result(data(), static_cast<size_t>(std::min<uint64_t>(buffer.required, capacity())));
        if (buffer.required > capacity()) result += " [capacity truncated]";
        else if (truncated) result += " [producer truncated]";
        return result;
    }
};

inline SrpSlice driver_slice(std::string_view bytes) noexcept
{
    return bytes.empty() ? SrpSlice{} : SrpSlice{reinterpret_cast<uintptr_t>(bytes.data()), bytes.size()};
}

template<class Entry, class AuthorityCheck>
class SynchronousDriver {
public:
    SynchronousDriver(Entry& entry, AuthorityCheck& authority, const Hooks& hooks)
        : entry_(entry), authority_(authority), hooks_(hooks) {}

    Result run(std::string_view path, std::string_view payload)
    {
        try {
            const auto denied = authority_();
            if (denied) throw std::runtime_error("record publication: bridge authority denied: " + std::to_string(denied));
            auto begin = request(SRP_BEGIN);
            begin.path = driver_slice(path);
            begin.payload = driver_slice(payload);
            const bool started = invoke(begin);
            if (!live_) {
                if (started) std::terminate(); // Successful BEGIN cannot lose ownership.
                return finish(); // Constructor/argument error: never replay BEGIN for text.
            }
            if (!started) recover();
            else read_text(begin, true);

            while (live_ && event_ != SRP_DONE) {
                if (aborted_ && event_ < SRP_BEFORE_CLEANUP) {
                    if (cancelled_) break;
                    cancel({});
                    if (event_ < SRP_BEFORE_CLEANUP) break; // RELEASE alone finalizes an incomplete cancellation.
                    continue;
                }
                if (event_ <= SRP_BEFORE_COMMIT) {
                    const auto denied_before_hook = authority_();
                    if (denied_before_hook) {
                        cancel("bridge authority denied: " + std::to_string(denied_before_hook));
                        continue;
                    }
                }
                std::optional<std::string> error;
                if (event_ != SRP_START) {
                    if (hook_events_ & (1u << event_)) break; // A failed cleanup continuation is retired, never replayed.
                    hook_events_ |= 1u << event_;
                    const auto& hook = hook_for(event_);
                    try { if (hook) hook(); }
                    catch (const std::exception& e) { error = e.what(); }
                    catch (...) { error = "unknown callback/native exception"; }
                }
                if (event_ <= SRP_BEFORE_COMMIT) {
                    const auto denied_after_hook = authority_();
                    if (error || denied_after_hook) {
                        if (error) cancel(*error);
                        else cancel("bridge authority denied: " + std::to_string(denied_after_hook));
                        continue;
                    }
                }
                auto next = request(SRP_ADVANCE);
                if (error) { next.reply = SRP_FAILED; next.hook_error = driver_slice(*error); }
                if (!invoke(next)) recover();
                else read_text(next, true);
            }
            retire(true);
            return finish();
        } catch (...) {
            // Also covers diagnostic allocation and throwing caller/Entry code.
            // Retirement recovery must itself be allocation-free on this path.
            const auto original = std::current_exception();
            if (live_) {
                try { snapshot(false); retire(false); }
                catch (...) { std::terminate(); }
            }
            if (committed_) {
                // Retirement did not require diagnostic allocation. A transient
                // failure may now permit a truthful Result: try representation
                // once, using the final response already copied before retirement.
                // Persistent failure must not escape as apparent noncommit.
                try {
                    if (!retired_response_) std::terminate();
                    read_text(*retired_response_, false);
                    // The bridge channel also exposes any retained native poison/
                    // transport bytes, including final RELEASE truncation markers.
                    append(bridge_error_, "bridge caller/diagnostic exception recovered after commit");
                    return finish();
                } catch (...) { std::terminate(); }
            }
            std::rethrow_exception(original);
        }
    }

private:
    SrpCall request(uint32_t opcode) noexcept
    {
        SrpCall call {};
        call.size = sizeof(call);
        call.abi = SRP_ABI;
        call.opcode = opcode;
        call.context = id_;
        call.sequence = sequence_;
        call.event = event_;
        call.primary_error = primary_channel_.buffer();
        call.cleanup_error = cleanup_channel_.buffer();
        call.transport_error = transport_channel_.buffer();
        return call;
    }

    // Only scalar work precedes the committed latch. Save id_ independently of
    // the frame: the PE authority guard deliberately clears denied responses.
    bool coherent_response(const SrpCall& call, uint32_t opcode) noexcept
    {
        const auto matches = [](const SrpBuffer& buffer, DriverChannel& channel) {
            return buffer.address == reinterpret_cast<uintptr_t>(channel.data()) && buffer.capacity == channel.capacity();
        };
        return call.size == sizeof(call) && call.abi == SRP_ABI && call.opcode == opcode
            && (call.flags & SRP_VALID) && !(call.flags & ~UINT32_C(255)) && call.context
            && call.event <= SRP_DONE && call.primary_state <= SRP_PRIMARY_PRESENT
            && bool(call.flags & SRP_DONE_FLAG) == (call.event == SRP_DONE)
            && (!(call.flags & SRP_COMMITTED) || call.event >= SRP_BEFORE_CLEANUP)
            && !call.reserved && !call.path.address && !call.path.size && !call.payload.address && !call.payload.size
            && !call.hook_error.address && !call.hook_error.size && call.reply == SRP_CONTINUE
            && matches(call.primary_error, primary_channel_) && matches(call.cleanup_error, cleanup_channel_)
            && matches(call.transport_error, transport_channel_);
    }

    bool coherent_begin(const SrpCall& call) noexcept
    {
        return coherent_response(call, SRP_BEGIN) && call.event == SRP_START && !call.sequence
            && call.flags == SRP_VALID && call.primary_state == SRP_PRIMARY_ABSENT
            && !call.primary_error.required && !call.cleanup_error.required && !call.transport_error.required;
    }

    bool invoke(SrpCall& call, bool diagnostics = true)
    {
        const auto opcode = call.opcode;
        const auto old_sequence = sequence_;
        const auto old_event = event_;
        if (opcode == SRP_RELEASE && ++release_attempts_ > 2) std::terminate();
        int32_t status;
        try { status = entry_(SRP_ENTRY_OPERATION, &call); }
        catch (...) {
            // Entry may throw after forwarding. Harvest only a coherent response,
            // without allocation, before the frame unwinds. Never replace a saved
            // ID with cleared denial fields or an untrusted response context.
            if (opcode == SRP_BEGIN && (call.context || (call.flags & SRP_VALID))) {
                if (!coherent_begin(call)) std::terminate();
                id_ = call.context;
                live_ = true;
            }
            if (coherent_response(call, opcode) && call.context == id_) {
                if (call.flags & SRP_COMMITTED) committed_ = true;
                sequence_ = call.sequence;
                event_ = call.event;
            }
            throw;
        }
        if (opcode == SRP_BEGIN && call.context) { id_ = call.context; live_ = true; }
        const bool valid = (call.flags & SRP_VALID) && call.context == id_ && id_
            && call.event <= SRP_DONE && call.primary_state <= SRP_PRIMARY_PRESENT
            && bool(call.flags & SRP_DONE_FLAG) == (call.event == SRP_DONE);
        if (valid && (call.flags & SRP_COMMITTED)) committed_ = true;
        const bool legal_event = opcode == SRP_SNAPSHOT
            || (opcode == SRP_BEGIN ? call.event == SRP_START
                : opcode == SRP_RELEASE ? call.event == SRP_DONE
                : opcode == SRP_CANCEL ? call.event >= SRP_BEFORE_CLEANUP
                : old_event < SRP_BEFORE_CLEANUP ? call.event == old_event + 1 || call.event >= SRP_BEFORE_CLEANUP
                : old_event == SRP_BEFORE_CLEANUP && call.event == SRP_DONE);
        const bool protocol = valid && coherent_response(call, opcode)
            && (!(committed_) || (call.flags & SRP_COMMITTED))
            && (status != SRP_SUCCESS || legal_event)
            && (opcode == SRP_SNAPSHOT || status != SRP_SUCCESS
                || (opcode == SRP_BEGIN ? call.sequence == 0 && call.event == SRP_START
                    : old_sequence != UINT64_MAX && call.sequence == old_sequence + 1));
        if (valid) { sequence_ = call.sequence; event_ = call.event; }
        // Success with final valid state is the adapter's retirement contract,
        // even with native cleanup_error or a sticky poison diagnostic.
        const bool retired = opcode == SRP_RELEASE && status == SRP_SUCCESS && protocol && event_ == SRP_DONE;
        if (retired) { live_ = false; retired_response_ = call; }
        const bool accepted = status == SRP_SUCCESS && protocol && (!(call.flags & SRP_POISONED) || retired || opcode == SRP_SNAPSHOT);
        if ((!accepted || (call.flags & SRP_POISONED)) && diagnostics) {
            if (!bridge_error_) bridge_error_ = "bridge opcode " + std::to_string(opcode)
                + " NTSTATUS " + std::to_string(status) + (protocol ? "" : " invalid response");
            read_text(call, false);
        }
        return accepted;
    }

    void read_text(const SrpCall& call, bool grow)
    {
        if (call.primary_state == SRP_PRIMARY_PRESENT)
            primary_ = primary_channel_.text(call.primary_error, call.flags & SRP_PRIMARY_TRUNCATED);
        if (call.flags & SRP_CLEANUP_PRESENT)
            cleanup_ = cleanup_channel_.text(call.cleanup_error, call.flags & SRP_CLEANUP_TRUNCATED);
        if (call.transport_error.required || (call.flags & SRP_POISONED)) {
            auto text = transport_channel_.text(call.transport_error, call.flags & SRP_TRANSPORT_TRUNCATED);
            // A transient validation diagnostic disappears on SNAPSHOT. Never
            // erase it with a different poison/finalization failure. Only a
            // fuller copy of the same capacity-truncated bytes may replace it.
            if (!transport_ || (transport_capacity_truncated_ && text.size() >= transport_prefix_
                    && transport_->compare(0, transport_prefix_, text, 0, transport_prefix_) == 0)) {
                transport_ = std::move(text);
                transport_prefix_ = static_cast<size_t>(std::min<uint64_t>(call.transport_error.required, transport_channel_.capacity()));
                transport_capacity_truncated_ = call.transport_error.required > transport_channel_.capacity();
            }
        }
        if (!grow || !live_) return; // Retiring RELEASE / no-context BEGIN cannot be queried again.
        bool enlarged = primary_channel_.grow(call.primary_error.required);
        enlarged = cleanup_channel_.grow(call.cleanup_error.required) || enlarged;
        enlarged = transport_channel_.grow(call.transport_error.required) || enlarged;
        if (enlarged) snapshot(true); // One growth per channel, only SNAPSHOT refills it.
    }

    void snapshot(bool diagnostics)
    {
        auto query = request(SRP_SNAPSHOT);
        if (!invoke(query, diagnostics)) std::terminate(); // Lost state or ownership cannot be guessed.
        if (query.flags & SRP_POISONED) aborted_ = true;
        if (diagnostics) read_text(query, true);
    }

    void recover()
    {
        aborted_ = true;
        snapshot(true);
    }

    void cancel(std::string_view reason)
    {
        aborted_ = true;
        cancelled_ = true;
        auto stop = request(SRP_CANCEL);
        stop.hook_error = driver_slice(reason);
        if (!invoke(stop)) recover();
        else read_text(stop, true);
    }

    void retire(bool diagnostics)
    {
        if (!live_) return;
        auto release = request(SRP_RELEASE);
        if (invoke(release, diagnostics)) {
            if (diagnostics) read_text(release, false);
            return;
        }
        // Exactly one snapshot-assisted cleanup-only retry. Never ADVANCE a
        // publication phase here and never discard the original bridge error.
        snapshot(diagnostics);
        auto retry = request(SRP_RELEASE);
        if (!invoke(retry, diagnostics)) std::terminate();
        if (diagnostics) read_text(retry, false);
    }

    const std::function<void()>& hook_for(uint32_t event) const
    {
        switch (event) {
        case SRP_BEFORE_WRITE: return hooks_.before_write;
        case SRP_BEFORE_SECURITY: return hooks_.before_security;
        case SRP_BEFORE_COMMIT: return hooks_.before_commit;
        case SRP_BEFORE_CLEANUP: return hooks_.before_cleanup;
        default: throw std::runtime_error("record publication: bridge unexpected hook event");
        }
    }

    static void append(std::optional<std::string>& output, std::string_view text)
    {
        if (output) { output->append("; "); output->append(text); }
        else output = std::string(text);
    }

    Result finish()
    {
        if (bridge_error_) {
            if (transport_) append(bridge_error_, *transport_);
            if (committed_) append(cleanup_, *bridge_error_);
            else if (primary_) append(primary_, *bridge_error_);
            else primary_ = *bridge_error_;
        }
        if (primary_) {
            if (committed_) append(cleanup_, *primary_);
            else {
                if (cleanup_) primary_->append("; cleanup: " + *cleanup_);
                throw std::runtime_error("record publication: " + *primary_);
            }
        }
        return {committed_, std::move(cleanup_)};
    }

    Entry& entry_;
    AuthorityCheck& authority_;
    const Hooks& hooks_;
    DriverChannel primary_channel_, cleanup_channel_, transport_channel_;
    uint64_t id_ = 0, sequence_ = 0;
    uint32_t event_ = SRP_START;
    uint32_t hook_events_ = 0;
    unsigned release_attempts_ = 0;
    size_t transport_prefix_ = 0;
    bool transport_capacity_truncated_ = false;
    bool live_ = false, committed_ = false, aborted_ = false, cancelled_ = false;
    std::optional<std::string> primary_, cleanup_, transport_, bridge_error_;
    std::optional<SrpCall> retired_response_;
};

template<class Entry, class AuthorityCheck>
Result drive(Entry&& entry, std::string_view host_path_bytes, std::string_view payload,
             const Hooks& hooks, AuthorityCheck&& authority_check)
{
    return SynchronousDriver<Entry, AuthorityCheck>(entry, authority_check, hooks).run(host_path_bytes, payload);
}

} // namespace record_publication::wine::detail
