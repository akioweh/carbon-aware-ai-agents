#ifndef SCHEDULING_QUEUE
#define SCHEDULING_QUEUE
#pragma once

#include "structs/JobRequest.hpp"
#include "structs/SchedulerOutput.hpp"
#include <atomic>
#include <boost/lockfree/queue.hpp>
#include <coroutine>

class SchedulerTask {
    std::atomic<std::coroutine_handle<>> taskHandle{nullptr};
    SchedulerOutput value;

  public:
    JobRequest jobRequest;
    SchedulerTask(JobRequest jobRequest) : jobRequest(std::move(jobRequest)) {};

    auto await_ready() -> bool { return false; }

    auto await_suspend(std::coroutine_handle<> handle) {
        taskHandle.store(handle, std::memory_order_release);
        taskHandle.notify_one();
    }

    auto await_resume() -> SchedulerOutput { return std::move(value); }

    auto setValue(SchedulerOutput result) { value = std::move(result); }

    auto resume() {
        taskHandle.wait(nullptr, std::memory_order_acquire);
        auto handle = taskHandle.load(std::memory_order_acquire);
        handle.resume();
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

#endif
