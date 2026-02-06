#ifndef CALENDAR
#define CALENDAR
#pragma once

#include "structs/ScheduleResult.hpp"
#include "structs/SchedulerOutput.hpp"

namespace calendarService {

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

auto get(time_point start = time_point::min(),
         time_point end = time_point::max())
    -> drogon::Task<std::vector<ScheduleBlock>>;

auto deleteSchedule(const std::string &jobId) -> drogon::Task<>;

}; // namespace calendarService

#endif
