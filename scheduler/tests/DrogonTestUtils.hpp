#ifndef DROGON_TEST_UTILS_HPP
#define DROGON_TEST_UTILS_HPP
#pragma once

#include <drogon/drogon.h>
#include <functional>
#include <future>
#include <thread>

// Global Drogon event loop manager for tests.
// Drogon's event loop can only be started once per process,
// so we manage a single persistent loop across all tests.
class DrogonTestRunner {
  public:
    static auto instance() -> DrogonTestRunner & {
        static DrogonTestRunner runner;
        return runner;
    }

    template <typename T>
    auto run(std::function<drogon::Task<T>()> coroFunc) -> T {
        std::promise<T> promise;
        auto future = promise.get_future();

        getLoop()->queueInLoop(
            [&promise, coroFunc = std::move(coroFunc)]() -> auto {
                drogon::async_run([&promise, coroFunc]() -> drogon::Task<void> {
                    try {
                        if constexpr (std::is_same_v<T, void>) {
                            co_await coroFunc();
                            promise.set_value();
                        } else {
                            T result = co_await coroFunc();
                            promise.set_value(std::move(result));
                        }
                    } catch (...) {
                        promise.set_exception(std::current_exception());
                    }
                });
            });

        return future.get();
    }

    // non-copyable, non-movable
    DrogonTestRunner(const DrogonTestRunner &) = delete;
    auto operator=(const DrogonTestRunner &) -> DrogonTestRunner & = delete;
    DrogonTestRunner(DrogonTestRunner &&) = delete;
    auto operator=(DrogonTestRunner &&) -> DrogonTestRunner & = delete;

  private:
    std::thread loopThread_;

    DrogonTestRunner() {
        loopThread_ = std::thread([]() -> void { drogon::app().run(); });

        while (!drogon::app().isRunning())
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    ~DrogonTestRunner() {
        drogon::app().quit();
        if (loopThread_.joinable())
            loopThread_.join();
    }

    static auto getLoop() -> trantor::EventLoop * {
        return drogon::app().getLoop();
    }
};

// Convenience function that uses the singleton runner
template <typename T>
auto run_coro_in_drogon(std::function<drogon::Task<T>()> coroFunc) -> T {
    return DrogonTestRunner::instance().run<T>(std::move(coroFunc));
}

#endif // DROGON_TEST_UTILS_HPP
