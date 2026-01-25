#ifndef DROGON_TEST_UTILS_HPP
#define DROGON_TEST_UTILS_HPP
#pragma once

#include <drogon/drogon.h>
#include <functional>
#include <future>
#include <thread>

// runs a coro in a working drogon event loop
// by spawning it in a new thread
// and waiting for it synchronously
template <typename T>
auto run_coro_in_drogon(std::function<drogon::Task<T>()> coroFunc) -> T {
    std::promise<T> promise;
    auto future = promise.get_future();

    std::thread drogonThread([&promise, coroFunc]() -> auto {
        drogon::app().getLoop()->queueInLoop([&promise, coroFunc]() -> auto {
            drogon::async_run([&promise, coroFunc]() -> drogon::Task<void> {
                try {
                    if constexpr (std::is_same_v<T, void>) {
                        co_await coroFunc();
                        promise.set_value();
                    } else {
                        T result = co_await coroFunc();
                        promise.set_value(result);
                    }
                } catch (...) {
                    promise.set_exception(std::current_exception());
                }
                drogon::app().quit();
            });
        });
        drogon::app().run();
    });

    drogonThread.join();
    return future.get();
}

#endif // DROGON_TEST_UTILS_HPP
