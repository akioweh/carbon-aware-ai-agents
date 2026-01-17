/*
 * i sure know what i am doing
 */

#ifndef SCHEDULER_UTIL_CORO
#define SCHEDULER_UTIL_CORO
#pragma once

#include "utils/Utils.hpp"
#include <atomic>
#include <coroutine>
#include <cstddef>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <expected>
#include <tuple>

namespace scheduler::coro {
namespace detail {

template <typename T> struct VectorResultContext {
    std::atomic<size_t> remaining;
    std::coroutine_handle<> continuation;
    std::vector<T> results;

    VectorResultContext(size_t cnt) : remaining(cnt), results(cnt) {}
};

template <typename... Ts> struct ResultContext {
    std::atomic<size_t> remaining;
    std::coroutine_handle<> continuation;
    std::tuple<Ts...> results;

    ResultContext(size_t cnt) : remaining(cnt) {}
};

template <typename Context>
    requires requires(Context ctx) {
        { ctx.remaining.load() } -> std::convertible_to<size_t>;
        { ctx.continuation } -> std::convertible_to<std::coroutine_handle<>>;
        { ctx.results };
    }
struct Awaiter {
    std::shared_ptr<Context> ctx;

    auto await_ready() -> bool { return ctx->remaining.load() == 0; }
    auto await_suspend(std::coroutine_handle<> handle) {
        ctx->continuation = handle;
    }
    auto await_resume() -> decltype(ctx->results) {
        return std::move(ctx->results);
    }
};

} // namespace detail

template <typename... Rets, bool return_exceptions = false,
          size_t N = sizeof...(Rets)>
auto when_all(drogon::Task<Rets>... coros)
    -> drogon::Task<std::tuple<std::conditional_t<
        return_exceptions, std::expected<Rets, std::exception_ptr>, Rets>...>> {
    auto ctx = std::make_shared<detail::ResultContext<std::conditional_t<
        return_exceptions, std::expected<Rets, std::exception_ptr>, Rets>...>>(
        N);

    [&]<std::size_t... Is>(std::index_sequence<Is...>) -> auto {
        ((drogon::async_run(
             [task = std::move(coros), ctx]() mutable -> drogon::Task<void> {
                 if constexpr (return_exceptions)
                     std::get<Is>(ctx->results) =
                         utils::pcall(drogon::async_func(task));
                 else
                     std::get<Is>(ctx->results) = co_await task;

                 if (ctx->remaining.fetch_sub(1) == 1)
                     ctx->continuation.resume();
             })),
         ...);
    }(std::make_index_sequence<N>{});

    co_return co_await detail::Awaiter{ctx};
}

template <typename T, bool return_exceptions = false>
auto when_all(std::vector<drogon::Task<T>> coros)
    -> drogon::Task<std::vector<std::conditional_t<
        return_exceptions, std::expected<T, std::exception_ptr>, T>>> {
    const auto n = coros.size();
    if (!n)
        co_return {};

    auto ctx = std::make_shared<detail::VectorResultContext<T>>(n);

    for (auto i = 0UZ; i < n; ++i) {
        drogon::async_run([i, task = std::move(coros[i]),
                           ctx]() mutable -> drogon::Task<void> {
            if constexpr (return_exceptions) // idk...
                ctx->results[i] = utils::pcall(drogon::async_func(task));
            else
                ctx->results[i] = co_await task;

            if (ctx->remaining.fetch_sub(1) == 1)
                ctx->continuation.resume();
        });
    }

    co_return co_await detail::Awaiter{ctx};
}

} // namespace scheduler::coro

#endif // SCHEDULER_UTIL_CORO
