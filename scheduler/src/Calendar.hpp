#ifndef SCHEDULER_CALENDAR_HPP
#define SCHEDULER_CALENDAR_HPP
#pragma once

#include "structs/ScheduleResult.hpp"
#include "structs/SchedulerOutput.hpp"
#include "utils/TimeGridder.hpp"
#include <drogon/orm/Criteria.h>

namespace scheduler::calendar {

template <typename T> auto to_task(auto awaitable) -> drogon::Task<T> {
    co_return co_await awaitable;
}

template <typename... Args>
auto combineCriteria(Args &&...criteria) -> drogon::orm::Criteria {
    return (std::forward<Args>(criteria) && ...);
}

constexpr auto ANY_DATACENTER = std::string{};

using time_point = std::chrono::system_clock::time_point;

/**
 * @brief Persists a scheduler output to the database.
 * @return The DB-assigned job ID as a string.
 */
auto add(const SchedulerOutput &output) -> drogon::Task<std::string>;

auto addTrivial(const SchedulerOutput &output,
                const std::string &scheduleIdString) -> drogon::Task<void>;

auto get(const std::string &scheduleIdString,
         const std::string &datacenter = ANY_DATACENTER)
    -> drogon::Task<ScheduleResult>;

auto getTrivial(const std::string &scheduleIdString,
                const std::string &datacenter = ANY_DATACENTER)
    -> drogon::Task<ScheduleResult>;

/**
 * get all scheduled blocks in a given time range
 */
auto get(time_point start = scheduler::utils::MIN_TIME,
         time_point end = scheduler::utils::MAX_TIME,
         const std::string &datacenter = ANY_DATACENTER)
    -> drogon::Task<std::vector<ScheduleBlock>>;

auto deleteSchedule(const std::string &scheduleId) -> drogon::Task<>;

/**
 * get a "summary" comprised of id, time frame, workload, and impact of every
 * scheduled job
 */
auto scheduleSummaries() -> drogon::Task<std::vector<ScheduleSummary>>;

}; // namespace scheduler::calendar

#endif // SCHEDULER_CALENDAR_HPP
