#include "structs/ScheduleBlock.hpp"
#include <Calendar.hpp>
#include <DtoMappers/Mappers.h>
#include <Scheduler.hpp>
#include <drogon/orm/Exception.h>
#include <mutex>
#include <ranges>
#include <utils/Utils.hpp>

auto CalendarService::add(Schedule schedule) -> drogon::Task<> {
    std::unique_lock lock(mutex);

    const auto transaction =
        co_await drogon::app().getDbClient()->newTransactionCoro();
    mappers::ImpactMapper impactMapper(transaction);
    mappers::JobMapper jobsMapper(transaction);

    const auto &[impact, intervals] = schedule;

    auto impactModel = mappers::toDto(impact);

    co_await impactMapper.insert(impactModel);
    const int impactId = impactModel.getValueOfId();

    for (auto &&jobModel :
         intervals |
             std::views::transform(mappers::toDto.withImpactId(impactId))) {
        co_await jobsMapper.insert(jobModel);
    }

    calendar[scheduler::utils::parseIntToStringID(impactId)] =
        std::move(schedule);
}

auto CalendarService::get(const std::string &jobIdString) -> drogon::Task<ScheduleResult> {
    std::shared_lock lock(mutex);

    auto result = calendar.find(jobIdString);
    if (result != calendar.end()) {
        auto [impact, schedule] = result->second;
        co_return ScheduleResult{.jobId = jobIdString,
                              .schedule = {schedule.begin(), schedule.end()},
                              .impact = impact};
    }

    auto dbPtr = drogon::app().getDbClient();
    mappers::ImpactMapper impactMapper(dbPtr);
    mappers::JobMapper jobsMapper(dbPtr);

    const int jobIdInt = scheduler::utils::parseStringIDtoInt(jobIdString);

    auto impact = mappers::fromDto(co_await impactMapper.findByPrimaryKey(jobIdInt));
    auto jobsModels = co_await jobsMapper.findBy(
        drogon::orm::Criteria(mappers::JobModel::Cols::_impact_id,
                              drogon::orm::CompareOperator::EQ, jobIdInt));
    auto jobs = mappers::fromDtoAll(jobsModels);

    auto stringJobId = scheduler::utils::parseIntToStringID(jobIdInt);
    calendar[stringJobId] = {impact, {jobs.begin(), jobs.end()}};

    co_return ScheduleResult{
        .jobId = stringJobId, .schedule = jobs, .impact = impact};
}

auto CalendarService::get() -> drogon::Task<Calendar> {
    std::shared_lock lock(mutex);
    auto dbPtr = drogon::app().getDbClient();
    mappers::ImpactMapper impactMapper(dbPtr);
    mappers::JobMapper jobsMapper(dbPtr);

    for (const auto &impactDto : co_await impactMapper.findAll()) {
        auto impact = mappers::fromDto(impactDto);
        calendar[scheduler::utils::parseIntToStringID(impactDto.getValueOfId())]
            .first = impact;
    }
    auto allJobs = mappers::fromDtoAll(co_await jobsMapper.findAll());
    for (const auto &job : allJobs) {
        calendar[job.jobId].second.insert(job);
    }
    co_return calendar;
}

auto CalendarService::deleteSchedule(const std::string &jobId) ->drogon::Task<> {
    auto dbPtr = drogon::app().getDbClient();
    mappers::ImpactMapper impactMapper(dbPtr);
    co_await impactMapper.deleteByPrimaryKey(
        scheduler::utils::parseStringIDtoInt(jobId));
    // we have cascade on delete, so no need to delete the children manually
    calendar.erase(jobId);
}