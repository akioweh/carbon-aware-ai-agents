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

template <typename T> struct VectorResultContext {
    std::atomic<size_t> remaining;
    std::coroutine_handle<> continuation;
    std::vector<T> results;
    std::mutex continuationMutex;
    bool continuationInstalled{false};
    bool resumePending{false};

    VectorResultContext(size_t cnt) : remaining(cnt), results(cnt) {}
};

template <typename... Ts> struct ResultContext {
    std::atomic<size_t> remaining{sizeof...(Ts)};
    std::coroutine_handle<> continuation;
    std::tuple<Ts...> results;
    std::mutex continuationMutex;
    bool continuationInstalled{false};
    bool resumePending{false};
};

template <typename Context>
    requires requires(Context ctx) {
        { ctx.remaining.load() } -> std::convertible_to<size_t>;
        { ctx.continuation } -> std::convertible_to<std::coroutine_handle<>>;
        { ctx.results };
    }
struct Awaiter {
    std::shared_ptr<Context> ctx;

    // if true, caller suspension and await_suspend() call are skipped
    auto await_ready() -> bool {
        return ctx->remaining.load(std::memory_order::acquire) == 0;
    }
    // executed after caller is suspended, with its handle
    auto await_suspend(std::coroutine_handle<> caller_handle) -> bool {
        auto resumeNow = false;
        {
            std::scoped_lock lock(ctx->continuationMutex);
            ctx->continuation = caller_handle;
            ctx->continuationInstalled = true;
            if (ctx->resumePending)
                resumeNow = true;
        }
        // return false to resume caller, true/void to suspend caller
        // if not returning false, we must handle.resume() later
        return !resumeNow;
    }
    // executed after caller is resumed (or if await_ready() == true)
    // to compute the value of the caller's "co_await this" expr
    auto await_resume() -> auto && { return std::move(ctx->results); }
};

} // namespace detail

template <typename... Rets, bool return_exceptions = false,
          size_t N = sizeof...(Rets)>
    requires(N > 0)
auto when_all(drogon::Task<Rets>... coros) -> detail::Awaiter<
    detail::ResultContext<detail::ResultType<Rets, return_exceptions>...>> {

    auto ctx = std::make_shared<detail::ResultContext<
        detail::ResultType<Rets, return_exceptions>...>>();

    auto launch_task =
        [&]<size_t Index, typename RetType,
            typename TaskType = drogon::Task<RetType>>(TaskType tsk) -> auto {
        drogon::async_run(
            [task = std::move(tsk), ctx]() mutable -> drogon::Task<void> {
                auto assign = [&](auto &&val) -> auto {
                    std::get<Index>(ctx->results) =
                        std::forward<decltype(val)>(val);
                };

                if constexpr (return_exceptions) {
                    try {
                        if constexpr (std::is_void_v<RetType>) {
                            co_await task;
                            assign({});
                        } else {
                            assign(co_await task);
                        }
                    } catch (...) {
                        assign(std::unexpected(std::current_exception()));
                    }
                } else {
                    if constexpr (std::is_void_v<RetType>) {
                        co_await task;
                        assign(std::monostate{});
                    } else {
                        assign(co_await task);
                    }
                }

                if (ctx->remaining.fetch_sub(1) == 1) {
                    bool resumeNow = false;
                    {
                        std::scoped_lock lock(ctx->continuationMutex);
                        if (ctx->continuationInstalled)
                            resumeNow = true;
                        else
                            ctx->resumePending = true;
                    }
                    if (resumeNow)
                        ctx->continuation.resume();
                }
            });
    };

    [&]<std::size_t... Is>(std::index_sequence<Is...>) -> auto {
        (launch_task.template operator()<Is, Rets>(std::move(coros)), ...);
    }(std::make_index_sequence<N>{});

    return detail::Awaiter{ctx};
}

template <typename T, bool return_exceptions = false>
auto when_all(std::vector<drogon::Task<T>> coros) -> detail::Awaiter<
    detail::VectorResultContext<detail::ResultType<T, return_exceptions>>> {
    const auto n = coros.size();

    auto ctx = std::make_shared<
        detail::VectorResultContext<detail::ResultType<T, return_exceptions>>>(
        n);

    for (auto &&[i, tsk] : std::views::enumerate(coros)) {
        drogon::async_run(
            [i, task = std::move(tsk), ctx]() mutable -> drogon::Task<void> {
                auto assign = [&](auto &&val) -> auto {
                    ctx->results[i] = std::forward<decltype(val)>(val);
                };

                if constexpr (return_exceptions) {
                    try {
                        if constexpr (std::is_void_v<T>) {
                            co_await task;
                            assign({});
                        } else {
                            assign(co_await task);
                        }
                    } catch (...) {
                        assign(std::unexpected(std::current_exception()));
                    }
                } else {
                    if constexpr (std::is_void_v<T>) {
                        co_await task;
                        assign(std::monostate{});
                    } else {
                        assign(co_await task);
                    }
                }

                if (ctx->remaining.fetch_sub(1) == 1) {
                    bool resumeNow = false;
                    {
                        std::scoped_lock lock(ctx->continuationMutex);
                        if (ctx->continuationInstalled)
                            resumeNow = true;
                        else
                            ctx->resumePending = true;
                    }
                    if (resumeNow)
                        ctx->continuation.resume();
                }
            });
    }

    return detail::Awaiter{ctx};
}

} // namespace scheduler::coro
#endif // SCHEDULER_UTIL_CORO
