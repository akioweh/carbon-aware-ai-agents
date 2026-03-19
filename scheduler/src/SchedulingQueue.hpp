#ifndef SCHEDULER_SCHEDULING_QUEUE_HPP
#define SCHEDULER_SCHEDULING_QUEUE_HPP
#include <exception>
#pragma once

#include "structs/JobRequest.hpp"
#include "structs/SchedulerOutput.hpp"
#include <atomic>
#include <boost/lockfree/queue.hpp>
#include <coroutine>

namespace scheduler {

class SchedulerTask {
    std::atomic<std::coroutine_handle<>> taskHandle{nullptr};
    enum class State { Pending, Suspended, Done };
    std::atomic<State> state{State::Pending};
    SchedulerOutput value;
    std::exception_ptr except_ptr{nullptr};

  public:
    JobRequest jobRequest;
    SchedulerTask(JobRequest jobRequest) : jobRequest(std::move(jobRequest)) {};

    auto await_ready() -> bool {
        return state.load(std::memory_order_acquire) == State::Done;
    }

    auto await_suspend(std::coroutine_handle<> handle) {
        taskHandle.store(handle, std::memory_order_release);
        auto expected = State::Pending;
        return state.compare_exchange_strong(expected, State::Suspended,
                                             std::memory_order_acq_rel);
    }

    auto await_resume() -> SchedulerOutput {
        if (except_ptr)
            std::rethrow_exception(except_ptr);
        return std::move(value);
    }

    auto setValue(SchedulerOutput result) { value = std::move(result); }

    auto resume() {

        auto expected = State::Pending;
        if (state.compare_exchange_strong(expected, State::Done,
                                          std::memory_order_acq_rel))
            return;

        auto handle = taskHandle.load(std::memory_order_acquire);
        handle.resume();
    }

    auto setException(auto &&e) { except_ptr = e; }
};

class SchedulingQueue {
    const static int initialSize = 32;
    using LockFreeQueue = boost::lockfree::queue<SchedulerTask *>;
    LockFreeQueue Q{initialSize};
    std::atomic<bool> running{false};
    std::atomic<int> queueSize{0};

    auto runTasks() -> drogon::Task<>;
    auto push_back(SchedulerTask *);

  public:
    SchedulingQueue() = default;
    auto computeSchedule(const JobRequest &) -> drogon::Task<SchedulerOutput>;

    SchedulingQueue(const SchedulingQueue &) = delete;
    SchedulingQueue(SchedulingQueue &&) = delete;
    auto operator=(const SchedulingQueue &) = delete;
    auto operator=(SchedulingQueue &&) = delete;
};

inline SchedulingQueue schedulingQueue{};

} // namespace scheduler

#endif // SCHEDULER_SCHEDULING_QUEUE_HPP
