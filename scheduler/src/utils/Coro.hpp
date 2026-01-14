#ifndef CORO
#define CORO

#include <atomic>
#include <coroutine>
#include <cstddef>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <iostream>
#include <vector>

namespace scheduler::coro {
namespace detail {
template <typename T> class Handler {
    std::vector<T> results;
    std::coroutine_handle<> whenAllHandle;
    std::atomic<size_t> activeJobsCounter;

  public:
    Handler(size_t numberOfJobs) : activeJobsCounter(numberOfJobs) {
        results.resize(numberOfJobs);
    }

    auto await_ready() -> bool { return false; }

    auto await_suspend(std::coroutine_handle<> injectedHandle) {
        whenAllHandle = injectedHandle;
    }

    auto await_resume() -> std::vector<T> { return std::move(results); }

    auto jobFinished() {
        if (activeJobsCounter.fetch_sub(1) == 1)
            resumeWhenAll();
    }

    auto resumeWhenAll() { whenAllHandle.resume(); }

    auto saveResult(size_t index, T value) {
        results[index] = std::move(value);
    }
};
} // namespace detail

template <typename T>
auto when_all(std::vector<drogon::Task<T>> jobs)
    -> drogon::Task<std::vector<T>> {
    auto numberOfJobs = jobs.size();
    auto manager = std::make_shared<detail::Handler<T>>(numberOfJobs);

    for (int index = 0; index < numberOfJobs; index++) {
        drogon::async_run([index, &jobs, manager]() -> drogon::Task<void> {
            auto job = std::move(jobs[index]);
            manager->saveResult(index, co_await job);
            manager->jobFinished();
            co_return;
        });
    }

    co_return co_await *manager;
}
} // namespace scheduler::coro

#endif