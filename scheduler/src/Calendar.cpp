#include "Calendar.hpp"
#include "Scheduler.hpp"
#include <expected>
#include <mutex>

auto CalendarService::add(const std::string &jobId, Schedule schedule) -> void {
    std::unique_lock lock(mutex);
    calendar[jobId] = std::move(schedule);
}

auto CalendarService::get(const std::string &jobId) const
    -> std::expected<Schedule, std::string> {
    std::shared_lock lock(mutex);

    auto result = calendar.find(jobId);
    if (result == calendar.end()) {
        return std::unexpected("trying to read a jobId that doesnt exist in "
                               "CalendarService get(jobId)");
    }
    return result->second;
}

auto CalendarService::get() const -> Calendar {
    std::shared_lock lock(mutex);
    return calendar;
}