#include "JobRequest.hpp"
#include <SchedulingQueue.hpp>
#include <atomic>
#include <coroutine>
#include <drogon/utils/coroutine.h>

auto SchedulingQueue::push_back(SchedulerTask *schedulerTask) {
    (void)queueSize.fetch_add(1, std::memory_order_release);
    while (!Q.push(schedulerTask))
        ;
    bool expected = false;
    if (running.compare_exchange_strong(expected, true)) {
        drogon::async_run([this]() -> drogon::Task<> {
            co_await runTasks();
            co_return;
        });
    }
}

auto SchedulingQueue::computeSchedule(const JobRequest &jobRequest)
    -> drogon::Task<std::pair<SchedulingImpact, std::set<ScheduledInterval>>> {
    auto schedulerTask = std::make_shared<SchedulerTask>(jobRequest) ;
    push_back(schedulerTask.get());
    co_return co_await *schedulerTask;
}

auto SchedulingQueue::runTasks() -> drogon::Task<> {
start:;
    SchedulerTask *task;
    while (Q.pop(task)) {
        (void)queueSize.fetch_sub(1, std::memory_order_release);

        Scheduler scheduler;
        auto impact = co_await scheduler.calculateSchedule(task->jobRequest);
        auto schedule = scheduler.getSchedule();
        task->setValue(impact, std::move(schedule));
        task->resume();
        // ok aparently this can break, if the coroutine gets destroyed
        // cause then the task points to garbage
        // however i dont really know how to solve it
        // cause then even the coroutine handle is bad, and its a pointer
        // so we cant know it points to garbage.
    }

    running.store(false, std::memory_order_release);

    if (queueSize.load(std::memory_order_acquire) > 0) {
        bool expected = false;
        if (running.compare_exchange_strong(expected, true)) {
            goto start;
        }
    }

    co_return ;
}