/*
 * i sure know what i am doing
 */

#ifndef SCHEDULER_UTIL_CORO
#define SCHEDULER_UTIL_CORO
#pragma once

#include <atomic>
#include <coroutine>
#include <cstddef>
#include <drogon/drogon.h>
#include <expected>
#include <memory>
#include <mutex>
#include <ranges>
#include <tuple>
#include <utility>
#include <variant>
#include <vector>

namespace scheduler::coro {
namespace detail {

// vector or tuple cannot hold void, so we use std::monostate
template <typename T>
using StorageType = std::conditional_t<std::is_void_v<T>, std::monostate, T>;

template <typename T, bool return_exceptions>
using ResultType =
    std::conditional_t<return_exceptions, std::expected<T, std::exception_ptr>,
                       StorageType<T>>;

// we done, but waiting for continuation to be installed
inline static const std::coroutine_handle<> WAITING_CONTINUATION =
    std::coroutine_handle<>::from_address(reinterpret_cast<void *>(1));
// no continuation installed yet (and not done)
inline static const std::coroutine_handle<> NO_CONTINUATION =
    std::coroutine_handle<>::from_address(nullptr);

template <typename ResultsContainer> struct ResultContext {
    std::atomic<size_t> remaining;
    std::atomic<std::coroutine_handle<>> continuation; // lock-free state repr
    ResultsContainer results;
    std::exception_ptr capturedException{nullptr};
    std::mutex exceptionMutex; // can we do this lock-free?

    explicit ResultContext(size_t cnt) : remaining(cnt), results(cnt) {}
    ResultContext() : remaining(std::tuple_size_v<ResultsContainer>) {};

    void capture_exception(std::exception_ptr ex) {
        std::scoped_lock lock{exceptionMutex};
        if (!capturedException)
            capturedException = std::move(ex);
    }

    // checks if all tasks are done, and resumes continuation if so
    void complete_one() {
        if (remaining.fetch_sub(1, std::memory_order::acq_rel) != 1)
            return;

        auto old_handle = continuation.exchange(WAITING_CONTINUATION,
                                                std::memory_order::acq_rel);
        if (old_handle.address() != nullptr)
            old_handle.resume();
    }
};

template <typename Context, bool return_exceptions> struct Awaiter {
    std::shared_ptr<Context> ctx;

    Awaiter(std::shared_ptr<Context> ctx) : ctx(std::move(ctx)) {}

    // if true, caller suspension and await_suspend() call are skipped
    auto await_ready() -> bool {
        return ctx->remaining.load(std::memory_order::acquire) == 0;
    }

    // executed after caller is suspended, with its handle.
    // return false to resume caller, true/void to suspend caller
    // if not returning false, we must handle.resume() later
    auto await_suspend(std::coroutine_handle<> caller_handle) -> bool {
        auto expected_handle = NO_CONTINUATION;
        return ctx->continuation.compare_exchange_strong(
            expected_handle, caller_handle, std::memory_order::acq_rel);
    }

    // executed after caller is resumed (or if await_ready() == true)
    // to compute the value of the caller's "co_await this" expr
    auto await_resume() -> auto && {
        if constexpr (!return_exceptions) {
            if (ctx->capturedException)
                std::rethrow_exception(ctx->capturedException);
        }
        return std::move(ctx->results);
    }
};

// run a function at end of scope
template <typename Func> struct ScopeGuard {
    Func func;
    ~ScopeGuard() { func(); }
};

template <bool return_exceptions, typename T>
void wrap_task(drogon::Task<T> task, auto ctx, auto assign) {
    drogon::async_run(
        [task = std::move(task), ctx,
         assign = std::move(assign)]() mutable -> drogon::Task<void> {
            ScopeGuard on_exit{[&] -> auto { ctx->complete_one(); }};

            try {
                if constexpr (std::is_void_v<T>) {
                    co_await task;
                    if (return_exceptions || !ctx->capturedException)
                        assign({});
                } else {
                    decltype(auto) result = co_await task;
                    if (return_exceptions || !ctx->capturedException)
                        assign(std::move(result));
                }
            } catch (...) {
                if constexpr (return_exceptions) {
                    assign(std::unexpected(std::current_exception()));
                } else {
                    ctx->capture_exception(std::current_exception());
                }
            }
        });
}

} // namespace detail

template <typename... Rets, bool return_exceptions = false,
          size_t N = sizeof...(Rets)>
    requires(N > 0)
auto when_all(drogon::Task<Rets>... coros) -> auto {
    using ResultsContainer =
        std::tuple<detail::ResultType<Rets, return_exceptions>...>;
    using Context = detail::ResultContext<ResultsContainer>;

    auto ctx = std::make_shared<Context>();

    [&]<std::size_t... Is>(std::index_sequence<Is...>) -> auto {
        (detail::wrap_task<return_exceptions>(
             std::move(coros), ctx,
             [ctx](auto &&val) -> auto {
                 std::get<Is>(ctx->results) = std::forward<decltype(val)>(val);
             }),
         ...);
    }(std::make_index_sequence<N>{});

    return detail::Awaiter<Context, return_exceptions>{ctx};
}

template <typename T, bool return_exceptions = false>
auto when_all(std::vector<drogon::Task<T>> coros) -> auto {
    const auto sz_ = coros.size();
    using ResultsContainer =
        std::vector<detail::ResultType<T, return_exceptions>>;
    using Context = detail::ResultContext<ResultsContainer>;

    auto ctx = std::make_shared<Context>(sz_);

    for (auto &&[i, tsk] : std::views::enumerate(coros)) {
        detail::wrap_task<return_exceptions>(
            std::move(tsk), ctx, [ctx, i](auto &&val) -> auto {
                ctx->results[i] = std::forward<decltype(val)>(val);
            });
    }

    return detail::Awaiter<Context, return_exceptions>{ctx};
}

} // namespace scheduler::coro
#endif // SCHEDULER_UTIL_CORO
