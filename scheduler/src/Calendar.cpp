#include "Calendar.hpp"
#include "DtoMappers/Mappers.h"
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

auto jobTimestampInsideTimeIntervalCriteria(time_point start, time_point end) {
    return drogon::orm::Criteria(mappers::JobModel::Cols::_time_stamp,
                                 drogon::orm::CompareOperator::GE,
                                 scheduler::utils::chronoToTrantor(start)) &&
           drogon::orm::Criteria(mappers::JobModel::Cols::_time_stamp,
                                 drogon::orm::CompareOperator::LT,
                                 scheduler::utils::chronoToTrantor(end));
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

auto get(const std::string &jobIdString) -> drogon::Task<ScheduleResult> {
    auto context = getContext();

    const int jobIdInt = scheduler::utils::parseStringIDtoInt(jobIdString);

    auto [impactModel, jobsModels] = co_await scheduler::coro::when_all(
        to_task<mappers::ImpactModel>(
            context.impactMapper.findByPrimaryKey(jobIdInt)),
        to_task<std::vector<mappers::JobModel>>(
            context.jobsMapper.findBy(jobImpactIdEqualityCriteria(jobIdInt))));

    auto impact = mappers::fromDto(impactModel);
    auto jobs = mappers::fromDtoAll(jobsModels);

    co_return ScheduleResult{
        .jobId = jobIdString, .schedule = jobs, .impact = impact};
}

auto get(time_point start, time_point end)
    -> drogon::Task<std::vector<ScheduleBlock>> {
    auto context = getContext();

    co_return mappers::fromDtoAll(co_await context.jobsMapper.findBy(
        jobTimestampInsideTimeIntervalCriteria(start, end)));
}

auto listJobs() -> drogon::Task<std::vector<std::string>> {
    auto context = getContext();
    auto res = co_await context.impactMapper.findAll();
    std::vector<std::string> jobIds;
    jobIds.reserve(res.size());
    for (const auto &item : res)
        jobIds.push_back(
            scheduler::utils::parseIntToStringID(item.getValueOfId()));
    co_return jobIds;
}

auto deleteSchedule(const std::string &jobId) -> drogon::Task<> {
    auto context = getContext();
    co_await context.impactMapper.deleteByPrimaryKey(
        scheduler::utils::parseStringIDtoInt(jobId));
    // we have cascade on delete, so no need to delete the children manually
}

} // namespace scheduler::calendar
