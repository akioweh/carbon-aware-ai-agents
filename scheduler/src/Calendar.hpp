#ifndef CALENDAR
#define CALENDAR
#pragma once

#include <Scheduler.hpp>
#include <expected>
#include <structs/ScheduledInterval.hpp>
#include <shared_mutex>

class CalendarService {
  private:
    using Schedule = std::pair<SchedulingImpact, std::set<ScheduledInterval>>;
    using Calendar = std::map<std::string, Schedule>;
    Calendar calendar;
    mutable std::shared_mutex mutex;

  public:
    auto add(const std::string &jobId, Schedule schedule) -> void;

    auto get(const std::string &jobId) const
        -> std::expected<Schedule, std::string>;

    auto get() const -> Calendar;

    CalendarService() = default;
    CalendarService(const CalendarService &) = delete;
    CalendarService(CalendarService &&) = delete;
    auto operator=(const CalendarService &) -> CalendarService & = delete;
    auto operator=(CalendarService &&) -> CalendarService & = delete;
};

inline CalendarService calendarService;

#endif
