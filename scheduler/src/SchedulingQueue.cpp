#include "Scheduler.hpp"
#include "SchedulingQueue.hpp"
#include "structs/JobRequest.hpp"
#include <drogon/utils/coroutine.h>

namespace scheduler {

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
    -> drogon::Task<SchedulerOutput> {
    auto schedulerTask = std::make_shared<SchedulerTask>(jobRequest);
    push_back(schedulerTask.get());
    co_return co_await *schedulerTask;
}

auto SchedulingQueue::runTasks() -> drogon::Task<> {
start:;
    SchedulerTask *task;
    while (Q.pop(task)) {
        (void)queueSize.fetch_sub(1, std::memory_order_release);

        Scheduler scheduler;
        auto res = co_await scheduler.scheduleJob(task->jobRequest);

        task->setValue(std::move(res));
        task->resume();
    }

    running.store(false, std::memory_order_release);

    if (queueSize.load(std::memory_order_acquire) > 0) {
        bool expected = false;
        if (running.compare_exchange_strong(expected, true)) {
            goto start;
        }
    }

    co_return;
}

} // namespace scheduler
