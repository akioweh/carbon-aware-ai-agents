#include "structs/ScheduleBlock.hpp"
#include <Calendar.hpp>
#include <DtoMappers/Mappers.h>
#include <Scheduler.hpp>
#include <expected>
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

auto CalendarService::get(const std::string &jobIdString) const
    -> drogon::Task<std::expected<ScheduleResult, std::string>> {
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
    try {
        auto impact = mappers::fromDto(impactMapper.findByPrimaryKey(jobIdInt));
        auto jobsModels = jobsMapper.findBy(
            drogon::orm::Criteria(mappers::JobModel::Cols::_impact_id,
                                  drogon::orm::CompareOperator::EQ, jobIdInt));
        auto jobs = jobsModels | std::views::transform(mappers::fromDto) |
                    std::ranges::to<std::vector>();

        co_return ScheduleResult{
            .jobId = scheduler::utils::parseIntToStringID(jobIdInt),
            .schedule = jobs,
            .impact = impact};

    } catch (const drogon::orm::DrogonDbException &e) {
        // Exceptions replace the error callback
        LOG_ERROR << "DB Error: " << e.base().what();
    }
}

auto CalendarService::get() const -> Calendar {
    std::shared_lock lock(mutex);
    return calendar;
}