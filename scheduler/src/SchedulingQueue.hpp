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

template <std::invocable Func> struct ScopeGuard {
    Func func;
    ~ScopeGuard() { func(); }
};

class SchedulerTask {
    std::atomic<std::coroutine_handle<>> taskHandle{nullptr};
    SchedulerOutput value;
    std::exception_ptr except_ptr{nullptr};
    std::atomic<bool> isDone{false};

  public:
    JobRequest jobRequest;
    SchedulerTask(JobRequest jobRequest) : jobRequest(std::move(jobRequest)) {};

    auto await_ready() -> bool {
        return isDone.load(std::memory_order_acquire);
    }

    auto await_suspend(std::coroutine_handle<> handle) {
        ScopeGuard onExitNotify{[&]() -> auto { taskHandle.notify_one(); }};
        taskHandle.store(handle, std::memory_order_release);
    }

    auto await_resume() -> SchedulerOutput {
        if (except_ptr) {
            std::cout << "AND WE SERVE IT BACK TO THE USER!" << std::endl;
            std::rethrow_exception(except_ptr);
        }
        return std::move(value);
    }

    auto setValue(SchedulerOutput result) {
        value = std::move(result);
        isDone.store(true, std::memory_order_release);
    }

    auto resume() {
        taskHandle.wait(nullptr, std::memory_order_acquire);
        auto handle = taskHandle.load(std::memory_order_acquire);
        handle.resume();
    }

    auto setException(auto &&e) {
        except_ptr = e;
        isDone.store(true, std::memory_order_release);
    }
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
