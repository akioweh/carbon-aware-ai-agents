#ifndef SCHEDULER_SCHEDULING_QUEUE_HPP
#define SCHEDULER_SCHEDULING_QUEUE_HPP
#pragma once

#include "SchedulerBase.hpp"
#include "structs/JobRequest.hpp"
#include "structs/SchedulerOutput.hpp"
#include <atomic>
#include <boost/lockfree/queue.hpp>
#include <coroutine>
#include <exception>
#include <memory>

namespace scheduler {

class SchedulerTask {
    std::atomic<std::coroutine_handle<>> taskHandle{nullptr};
    enum class State { Pending, Suspended, Done };
    std::atomic<State> state{State::Pending};
    SchedulerOutput value;
    std::exception_ptr except_ptr{nullptr};

  public:
    std::unique_ptr<SchedulerBase> scheduler;
    JobRequest jobRequest;

    SchedulerTask(std::unique_ptr<SchedulerBase> sched, JobRequest jobRequest)
        : scheduler(std::move(sched)), jobRequest(std::move(jobRequest)) {};

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
    void push_back(SchedulerTask *);

  public:
    // Sched must be a subclass of SchedulerBase
    template <typename Sched>
    auto computeSchedule(const JobRequest &jobRequest)
        -> drogon::Task<SchedulerOutput> {
        auto schedulerTask = std::make_shared<SchedulerTask>(
            std::make_unique<Sched>(), jobRequest);
        push_back(schedulerTask.get());
        co_return co_await *schedulerTask;
    }

    SchedulingQueue() = default;
    SchedulingQueue(const SchedulingQueue &) = delete;
    SchedulingQueue(SchedulingQueue &&) = delete;
    auto operator=(const SchedulingQueue &) = delete;
    auto operator=(SchedulingQueue &&) = delete;
};

inline SchedulingQueue schedulingQueue{};

} // namespace scheduler

#endif // SCHEDULER_SCHEDULING_QUEUE_HPP
