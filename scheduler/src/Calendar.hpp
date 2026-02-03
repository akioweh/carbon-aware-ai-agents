#ifndef CALENDAR
#define CALENDAR
#pragma once

#include <Scheduler.hpp>
#include <expected>
#include <models/Impacts.h>
#include <models/Jobs.h>
#include <shared_mutex>
#include <structs/ScheduleBlock.hpp>

class CalendarService {
  public:
    using Schedule = std::pair<ScheduleImpact, std::set<ScheduleBlock>>;
    using Calendar = std::map<std::string, Schedule>;
    auto add(Schedule schedule) -> void;

    auto get(const std::string &jobId) const
        -> drogon::Task<std::expected<ScheduleResult, std::string>>;

    auto get() const -> Calendar;

    CalendarService() = default;
    CalendarService(const CalendarService &) = delete;
    CalendarService(CalendarService &&) = delete;
    auto operator=(const CalendarService &) -> CalendarService & = delete;
    auto operator=(CalendarService &&) -> CalendarService & = delete;

  private:
    Calendar calendar;
    mutable std::shared_mutex mutex;
};

inline CalendarService calendarService;

#endif
