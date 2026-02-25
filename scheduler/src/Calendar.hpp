#ifndef SCHEDULER_CALENDAR_HPP
#define SCHEDULER_CALENDAR_HPP
#include "utils/TimeGridder.hpp"
#include <cstddef>
#include <drogon/orm/Criteria.h>
#pragma once

#include "structs/ScheduleResult.hpp"
#include "structs/SchedulerOutput.hpp"

namespace scheduler::calendar {

template <typename T> auto to_task(auto awaitable) -> drogon::Task<T> {
    co_return co_await awaitable;
}

template <typename... Args>
auto combineCriteria(Args &&...criteria) -> drogon::orm::Criteria {
    return (std::forward<Args>(criteria) && ...);
}

constexpr std::string ANY_DATACENTER{};

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

auto get(time_point start = scheduler::utils::MIN_TIME,
         time_point end = scheduler::utils::MAX_TIME,
         const std::string &datacenter = ANY_DATACENTER)
    -> drogon::Task<std::vector<ScheduleBlock>>;

auto deleteSchedule(const std::string &scheduleId) -> drogon::Task<>;

auto scheduleSummaries() -> drogon::Task<std::vector<ScheduleSummary>>;

}; // namespace scheduler::calendar

#endif // SCHEDULER_CALENDAR_HPP
