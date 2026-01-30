#include "Calendar.hpp"
#include "Scheduler.hpp"
#include <expected>
#include <mutex>
#include <models/Impacts.h>
#include <models/Jobs.h>

using JobModel = drogon_model::calendar_db::Jobs ;
using ImpactModel = drogon_model::calendar_db::Impacts ;

using JobMapper = drogon::orm::Mapper<JobModel>;
using ImpactMapper = drogon::orm::Mapper<ImpactModel>;

auto CalendarService::add(const std::string &jobId, Schedule schedule) -> void {
    std::unique_lock lock(mutex);
    calendar[jobId] = std::move(schedule);
    
    const auto dbPtr = drogon::app().getFastDbClient(); 
    ImpactMapper impactMapper(dbPtr) ;
    JobMapper jobsMapper(dbPtr) ;
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