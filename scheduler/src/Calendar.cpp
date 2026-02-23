#include "Calendar.hpp"
#include "DtoMappers/Mappers.h"
#include "exceptions/ValidationException.hpp"
#include "structs/ScheduleResult.hpp"
#include "utils/Coro.hpp"
#include "utils/Utils.hpp"
#include <drogon/orm/Criteria.h>
#include <drogon/orm/Exception.h>
#include <ranges>

namespace scheduler::calendar {

using namespace scheduler;

namespace {

struct Context {
    mappers::ImpactMapper impactMapper;
    mappers::JobMapper jobsMapper;
    explicit Context(const drogon::orm::DbClientPtr &db)
        : impactMapper(db), jobsMapper(db) {}
};

auto getContext() { return Context(drogon::app().getDbClient()); }

auto jobImpactIdEqualityCriteria(const int impactId) {
    return drogon::orm::Criteria(mappers::JobModel::Cols::_impact_id,
                                 drogon::orm::CompareOperator::EQ, impactId);
}

auto jobTimestampAfterStartCriteria(time_point start) {
    return drogon::orm::Criteria(mappers::JobModel::Cols::_time_stamp,
                                 drogon::orm::CompareOperator::GE,
                                 scheduler::utils::chronoToTrantor(start));
}

auto jobTimestampBeforeEndCriteria(time_point end) {
    return drogon::orm::Criteria(mappers::JobModel::Cols::_time_stamp,
                                 drogon::orm::CompareOperator::LT,
                                 scheduler::utils::chronoToTrantor(end));
}

auto specificDatacenterCriteria(const std::string &datacenter) {
    if (datacenter == ANY_DATACENTER)
        return drogon::orm::Criteria();
    return drogon::orm::Criteria(mappers::JobModel::Cols::_location_id,
                                 drogon::orm::CompareOperator::EQ, datacenter);
}

} // namespace

auto add(const SchedulerOutput &output) -> drogon::Task<std::string> {
    auto transaction =
        co_await drogon::app().getDbClient()->newTransactionCoro();
    Context context(transaction);

    auto impactModel = mappers::toDto(output.impact);
    impactModel = co_await context.impactMapper.insert(impactModel);
    const auto impactId = impactModel.getValueOfId();

    for (auto &&jobModel :
         output.blocks |
             std::views::transform(mappers::toDto.withImpactId(impactId))) {
        co_await context.jobsMapper.insert(jobModel);
    }

    co_return scheduler::utils::parseIntToStringID(impactId);
}

auto get(const std::string &scheduleIdString, const std::string &datacenter)
    -> drogon::Task<ScheduleResult> {
    auto context = getContext();

    const int jobIdInt = scheduler::utils::parseStringIDtoInt(scheduleIdString);

    try {
        const auto fullCriteria =
            combineCriteria(jobImpactIdEqualityCriteria(jobIdInt),
                            specificDatacenterCriteria(datacenter));

        auto &&[impactModel, jobsModels] = co_await scheduler::coro::when_all(
            to_task<mappers::ImpactModel>(
                context.impactMapper.findByPrimaryKey(jobIdInt)),
            to_task<std::vector<mappers::JobModel>>(
                context.jobsMapper.findBy(fullCriteria)));

        co_return ScheduleResult{.scheduleId = scheduleIdString,
                                 .schedule = mappers::fromDtoAll(jobsModels),
                                 .impact = mappers::fromDto(impactModel)};
    } catch (const std::exception &e) {
        LOG_ERROR << "NO scheduled job with id=" + scheduleIdString
                  << " in the DB!";
        throw scheduler::exceptions::ValidationException(
            "No scheduled job with id: " + scheduleIdString);
    }
}

auto get(time_point start, time_point end, const std::string &datacenter)
    -> drogon::Task<std::vector<ScheduleBlock>> {
    auto context = getContext();

    const auto fullCriteria =
        combineCriteria(jobTimestampAfterStartCriteria(start),
                        jobTimestampBeforeEndCriteria(end),
                        specificDatacenterCriteria(datacenter));

    co_return mappers::fromDtoAll(
        co_await context.jobsMapper.findBy(fullCriteria));
}

auto scheduleSummaries() -> drogon::Task<std::vector<ScheduleSummary>> {
    auto context = getContext();
    auto res = co_await context.impactMapper.findAll();
    std::vector<ScheduleSummary> scheduleSummaries;
    scheduleSummaries.reserve(res.size());
    for (const auto &item : res)
        scheduleSummaries.push_back(
            {.scheduleId =
                 scheduler::utils::parseIntToStringID(item.getValueOfId()),
             .impact = scheduler::mappers::fromDto(item)});
    co_return scheduleSummaries;
}

auto deleteSchedule(const std::string &scheduleId) -> drogon::Task<> {
    auto context = getContext();
    co_await context.impactMapper.deleteByPrimaryKey(
        scheduler::utils::parseStringIDtoInt(scheduleId));
    // we have cascade on delete, so no need to delete the children manually
}

} // namespace scheduler::calendar
