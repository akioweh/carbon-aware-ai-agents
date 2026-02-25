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
    mappers::TrivialImpactMapper trivialImpactMapper;
    mappers::TrivialJobMapper trivialJobsMapper;
    explicit Context(const drogon::orm::DbClientPtr &db)
        : impactMapper(db), jobsMapper(db), trivialImpactMapper(db), trivialJobsMapper(db) {}
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

auto trivialJobImpactIdEqualityCriteria(const int impactId) {
    return drogon::orm::Criteria(mappers::TrivialJobModel::Cols::_trivial_impact_id,
                                 drogon::orm::CompareOperator::EQ, impactId);
}

auto specificTrivialDatacenterCriteria(const std::string &datacenter) {
    if (datacenter == ANY_DATACENTER)
        return drogon::orm::Criteria();
    return drogon::orm::Criteria(mappers::TrivialJobModel::Cols::_location_id,
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

auto addTrivial(const SchedulerOutput &output, const std::string &scheduleIdString) -> drogon::Task<void> {
    auto transaction =
        co_await drogon::app().getDbClient()->newTransactionCoro();
    Context context(transaction);

    int impactId = scheduler::utils::parseStringIDtoInt(scheduleIdString);
    
    auto trivialImpactModel = mappers::toTrivialDto.withImpactId(impactId)(output.impact);
    trivialImpactModel = co_await context.trivialImpactMapper.insert(trivialImpactModel);
    const auto trivialImpactId = trivialImpactModel.getValueOfId();

    for (auto &&trivialJobModel :
         output.blocks |
             std::views::transform(mappers::toTrivialDto.withTrivialImpactId(trivialImpactId))) {
        co_await context.trivialJobsMapper.insert(trivialJobModel);
    }
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

auto getTrivial(const std::string &scheduleIdString, const std::string &datacenter)
    -> drogon::Task<std::optional<ScheduleResult>> {
    auto context = getContext();

    const int jobIdInt = scheduler::utils::parseStringIDtoInt(scheduleIdString);

    try {
        const auto impactCriteria =
            drogon::orm::Criteria(mappers::TrivialImpactModel::Cols::_impact_id,
                                 drogon::orm::CompareOperator::EQ, jobIdInt);

        auto trivialImpactModels = co_await context.trivialImpactMapper.findBy(impactCriteria);
        if (trivialImpactModels.empty()) {
            co_return std::nullopt;
        }
        auto impactModel = trivialImpactModels.front();
        const int trivialImpactId = impactModel.getValueOfId();

        const auto fullCriteria =
            combineCriteria(trivialJobImpactIdEqualityCriteria(trivialImpactId),
                            specificTrivialDatacenterCriteria(datacenter));

        auto jobsModels = co_await context.trivialJobsMapper.findBy(fullCriteria);

        co_return ScheduleResult{.scheduleId = scheduleIdString,
                                 .schedule = mappers::fromTrivialDtoAll(jobsModels, jobIdInt),
                                 .impact = mappers::fromDto(impactModel)};
    } catch (const std::exception &e) {
        LOG_ERROR << "Error fetching trivial schedule with id=" + scheduleIdString;
        co_return std::nullopt;
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
    
    // Also fetch trivial impacts if any
    auto trivialRes = co_await context.trivialImpactMapper.findAll();
    std::unordered_map<int, mappers::TrivialImpactModel> trivialMap;
    for (const auto &item : trivialRes) {
        trivialMap[item.getValueOfImpactId()] = item;
    }
    
    std::vector<ScheduleSummary> scheduleSummaries;
    scheduleSummaries.reserve(res.size());
    for (const auto &item : res) {
        int impactId = item.getValueOfId();
        ScheduleSummary summary{
            .scheduleId = scheduler::utils::parseIntToStringID(impactId),
            .impact = scheduler::mappers::fromDto(item)
        };
        
        if (trivialMap.contains(impactId)) {
            summary.trivialImpact = scheduler::mappers::fromDto(trivialMap[impactId]);
        }
        
        scheduleSummaries.push_back(summary);
    }
    co_return scheduleSummaries;
}

auto deleteSchedule(const std::string &scheduleId) -> drogon::Task<> {
    auto context = getContext();
    co_await context.impactMapper.deleteByPrimaryKey(
        scheduler::utils::parseStringIDtoInt(scheduleId));
    // we have cascade on delete, so no need to delete the children manually
}

} // namespace scheduler::calendar
