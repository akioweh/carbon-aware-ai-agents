#ifndef SCHEDULER_CALENDAR_HPP
#define SCHEDULER_CALENDAR_HPP
#include "utils/TimeGridder.hpp"
#pragma once

#include "structs/ScheduleResult.hpp"
#include "structs/SchedulerOutput.hpp"

namespace scheduler::calendar {

template <typename T> auto to_task(auto awaitable) -> drogon::Task<T> {
    co_return co_await awaitable;
}

using time_point = std::chrono::system_clock::time_point;

/**
 * @brief Persists a scheduler output to the database.
 * @return The DB-assigned job ID as a string.
 */
auto add(const SchedulerOutput &output) -> drogon::Task<std::string>;

auto get(const std::string &jobId) -> drogon::Task<ScheduleResult>;

auto get(time_point start = scheduler::utils::MIN_TIME,
         time_point end = scheduler::utils::MAX_TIME)
    -> drogon::Task<std::vector<ScheduleBlock>>;

auto deleteSchedule(const std::string &jobId) -> drogon::Task<>;

auto listJobs() -> drogon::Task<std::vector<std::string>>;

}; // namespace scheduler::calendar

#endif // SCHEDULER_CALENDAR_HPP
