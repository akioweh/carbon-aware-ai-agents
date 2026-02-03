#include "structs/ScheduleBlock.hpp"
#include <Calendar.hpp>
#include <DtoMappers/Mappers.h>
#include <Scheduler.hpp>
#include <mutex>
#include <ranges>
#include <utils/Utils.hpp>

auto CalendarService::add(Schedule schedule) -> void {
    std::unique_lock lock(mutex);

    const auto transaction =
        drogon::app().getDbClient()->newTransaction([](bool success) -> void {
            if (!success) {
                LOG_ERROR << "Transaction failed!" << '\n';
            }
        });
    mappers::ImpactMapper impactMapper(transaction);
    mappers::JobMapper jobsMapper(transaction);

    const auto &[impact, intervals] = schedule;

    auto impactModel = mappers::toDto(impact);

    impactMapper.insert(impactModel);
    const int impactId = impactModel.getValueOfId();

    for (auto &&jobModel :
         intervals |
             std::views::transform(mappers::toDto.withImpactId(impactId))) {
        jobsMapper.insert(jobModel);
    }

    calendar[scheduler::utils::parseIntToStringID(impactId)] =
        std::move(schedule);
}

auto CalendarService::get(const std::string &jobIdString)
    -> ScheduleResult {
    std::shared_lock lock(mutex);

    auto result = calendar.find(jobIdString);
    if (result != calendar.end()) {
        auto [impact, schedule] = result->second;
        return ScheduleResult{.jobId = jobIdString,
                              .schedule = {schedule.begin(), schedule.end()},
                              .impact = impact};
    }

    auto dbPtr = drogon::app().getDbClient();
    mappers::ImpactMapper impactMapper(dbPtr);
    mappers::JobMapper jobsMapper(dbPtr);

    const int jobIdInt = scheduler::utils::parseStringIDtoInt(jobIdString);

    auto impact = mappers::fromDto(impactMapper.findByPrimaryKey(jobIdInt));
    auto jobsModels = jobsMapper.findBy(
        drogon::orm::Criteria(mappers::JobModel::Cols::_impact_id,
                                drogon::orm::CompareOperator::EQ, jobIdInt));
    auto jobs = mappers::fromDtoAll(jobsModels);

    auto stringJobId = scheduler::utils::parseIntToStringID(jobIdInt);
    calendar[stringJobId] = {impact, {jobs.begin(), jobs.end()}};

    return ScheduleResult{
        .jobId = stringJobId, .schedule = jobs, .impact = impact};
}

auto CalendarService::get() -> Calendar {
    std::shared_lock lock(mutex);
    auto dbPtr = drogon::app().getDbClient();
    mappers::ImpactMapper impactMapper(dbPtr);
    mappers::JobMapper jobsMapper(dbPtr);

    for (const auto &impactDto : impactMapper.findAll()) {
        auto impact = mappers::fromDto(impactDto);
        calendar[scheduler::utils::parseIntToStringID(
                        impactDto.getValueOfId())]
            .first = impact;
    }
    auto allJobs = mappers::fromDtoAll(jobsMapper.findAll());
    for (const auto &job : allJobs) {
        calendar[job.jobId].second.insert(job);
    }

    return calendar;
}