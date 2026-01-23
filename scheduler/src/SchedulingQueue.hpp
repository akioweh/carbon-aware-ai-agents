#ifndef SCHEDULING_QUEUE
#define SCHEDULING_QUEUE
#include "ScheduledInterval.hpp"
#include <atomic>
#include <coroutine>
#pragma once

#include <JobRequest.hpp>
#include <Scheduler.hpp>
#include <boost/lockfree/queue.hpp>

class SchedulerTask {
    std::atomic<std::coroutine_handle<>> taskHandle{nullptr};
    using Value = std::pair<SchedulingImpact, std::set<ScheduledInterval>>;
    Value value;

  public:
    JobRequest jobRequest;
    SchedulerTask(JobRequest jobRequest) : jobRequest(std::move(jobRequest)) {};

    auto await_ready() -> bool { return false; }

    auto await_suspend(std::coroutine_handle<> handle) {
        taskHandle.store(handle, std::memory_order_release);
        taskHandle.notify_one();
    }

    auto await_resume() -> Value { return std::move(value); }

    auto setValue(SchedulingImpact impact,
                  std::set<ScheduledInterval> &&schedule) {
        value = {impact, std::move(schedule)};
    }

    auto resume() {
        taskHandle.wait(nullptr, std::memory_order_acquire);
        auto handle = taskHandle.load(std::memory_order_acquire);
        handle.resume();
    }
};

class SchedulingQueue {
    const static int initialSize = 32;
    using LockFreeQueue = boost::lockfree::queue<SchedulerTask *>;
    LockFreeQueue Q;
    std::atomic<bool> running{false};
    std::atomic<int> queueSize{0};

    auto runTasks() -> drogon::Task<>;
    auto push_back(SchedulerTask *);

  public:
    SchedulingQueue() : Q(initialSize) {};
    auto computeSchedule(const JobRequest &) -> drogon::Task<
        std::pair<SchedulingImpact, std::set<ScheduledInterval>>>;
};

#endif