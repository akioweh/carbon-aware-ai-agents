#include "Calendar.hpp"
#include "Scheduler.hpp"
#include <expected>
#include <models/Impacts.h>
#include <models/Jobs.h>
#include <mutex>
#include <trantor/utils/Date.h>
#include <utils/Utils.hpp>

using JobModel = drogon_model::calendar_db::Jobs;
using ImpactModel = drogon_model::calendar_db::Impacts;

using JobMapper = drogon::orm::Mapper<JobModel>;
using ImpactMapper = drogon::orm::Mapper<ImpactModel>;

auto CalendarService::add(const std::string &jobId, Schedule schedule) -> void {
    std::unique_lock lock(mutex);

    const auto dbPtr = drogon::app().getDbClient();
    ImpactMapper impactMapper(dbPtr);
    JobMapper jobsMapper(dbPtr);

    const auto &[impact, intervals] = schedule;

    ImpactModel impactDB;
    impactDB.setCarbonIntensity(impact.carbon_intensity);
    impactDB.setSci(impact.sci);
    impactDB.setTotalEmissions(impact.total_emissions);
    // can refactor this later to other function

    impactMapper.insert(impactDB);
    const int impactId = *impactDB.getId();

    std::vector<JobModel> jobsBatch;
    for (const auto &interval : intervals) {
        JobModel job;
        job.setAdditionalLoad(interval.additionalLoad);
        job.setTotalLoad(interval.totalLoad);
        job.setLocationId(interval.location);
        job.setImpactId(impactId);
        job.setTimeStamp(
            scheduler::utils::getPostGreDateFormat(interval.timestamp));
        jobsMapper.insert(job);
        /// this can also be refactored
        jobsBatch.push_back(std::move(job));
    }

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