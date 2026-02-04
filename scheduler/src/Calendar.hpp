#ifndef CALENDAR
#define CALENDAR
#pragma once

#include <Scheduler.hpp>
#include <models/Impacts.h>
#include <models/Jobs.h>
#include <structs/ScheduleBlock.hpp>

namespace calendarService {

template <typename T> auto to_task(auto awaitable) -> drogon::Task<T> {
    co_return co_await awaitable;
}

using Schedule = std::pair<ScheduleImpact, std::set<ScheduleBlock>>;
using time_point = std::chrono::system_clock::time_point;

auto add(Schedule schedule) -> drogon::Task<>;

auto get(const std::string &jobId) -> drogon::Task<ScheduleResult>;

auto get(time_point start = time_point::min(),
         time_point end = time_point::max()) -> drogon::Task<std::vector<ScheduleBlock>>;

auto deleteSchedule(const std::string &jobId) -> drogon::Task<>;

}; // namespace calendarService

#endif
