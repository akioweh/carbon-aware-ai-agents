#include <Calendar.hpp>
#include <SchedulingQueue.hpp>
#include <atomic>
#include <drogon/utils/coroutine.h>
#include <structs/JobRequest.hpp>

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
    -> drogon::Task<ScheduleResult> {
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
        auto schedule = std::set<ScheduleBlock>{};

        auto persist = [impact = res.impact, schedule]() mutable -> void {
            if (schedule.size() == 0) {
                LOG_WARN
                    << "the size of a scheduled job is zero - not persisiting";
                return;
            }
            const auto &first = *schedule.begin();
            const auto jobId = first.jobId;
            calendarService.add(jobId, {impact, std::move(schedule)});
        };

        task->setValue(res);
        task->resume();

        // ok aparently this can break, if the coroutine gets destroyed
        // cause then the task points to garbage
        // however i dont really know how to solve it
        // cause then even the coroutine handle is bad, and its a pointer
        // so we cant know it points to garbage.
        drogon::async_run([persist]() mutable -> drogon::Task<> {
            persist();
            co_return;
        });
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
