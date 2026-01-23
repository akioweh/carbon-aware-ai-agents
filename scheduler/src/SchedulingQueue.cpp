#include "JobRequest.hpp"
#include <SchedulingQueue.hpp>
#include <atomic>
#include <coroutine>
#include <drogon/utils/coroutine.h>

auto SchedulingQueue::push_back(SchedulerTask *schedulerTask) {
    while(!Q.push(schedulerTask));
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
    SchedulerTask schedulerTask(jobRequest);
    push_back(&schedulerTask);
    co_return co_await schedulerTask;
}

auto SchedulingQueue::runTasks() -> drogon::Task<> {
    SchedulerTask *task;
    while (Q.pop(task)) {
        Scheduler scheduler;
        auto impact = co_await scheduler.calculateSchedule(task->jobRequest);
        auto schedule = scheduler.getSchedule();
        task->setValue(impact, std::move(schedule));
        task->resume();
    }

    running.store(false);

    if (Q.pop(task)) {
        push_back(task) ;
        // this is needed cause someone might have pushed and checked before
        // running was false, but after the queue was already empty. 
        // In that case we have to put it back to the queue.
        // We cant use .empty() cause of visiblity issues.
        // Con is that it goes back to the back of the queue, 
        // but i can elaborate why i dont think we can do differently.
    }
}