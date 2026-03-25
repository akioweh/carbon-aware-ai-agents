#include "Calendar.hpp"
#include "DtoMappers/Mappers.h"
#include "exceptions/SchedulingException.hpp"
#include "exceptions/ValidationException.hpp"
#include "structs/ScheduleResult.hpp"
#include "utils/Coro.hpp"
#include "utils/Utils.hpp"
#include <drogon/orm/Criteria.h>
#include <drogon/orm/Exception.h>
#include <ranges>
#include <string>
#include <unordered_map>

namespace scheduler::calendar {

using namespace std;
using namespace drogon;

using namespace scheduler;

namespace {

struct Context {
    mappers::ImpactMapper impactMapper;
    mappers::JobMapper jobsMapper;
    mappers::TrivialImpactMapper trivialImpactMapper;
    mappers::TrivialJobMapper trivialJobsMapper;
    explicit Context(const drogon::orm::DbClientPtr &db)
        : impactMapper(db), jobsMapper(db), trivialImpactMapper(db),
          trivialJobsMapper(db) {}
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

auto specificDatacenterCriteria(const string &datacenter) {
    if (datacenter == ANY_DATACENTER)
        return drogon::orm::Criteria();
    return drogon::orm::Criteria(mappers::JobModel::Cols::_location_id,
                                 drogon::orm::CompareOperator::EQ, datacenter);
}

auto trivialJobImpactIdEqualityCriteria(const int impactId) {
    return drogon::orm::Criteria(
        mappers::TrivialJobModel::Cols::_trivial_impact_id,
        drogon::orm::CompareOperator::EQ, impactId);
}

auto specificTrivialDatacenterCriteria(const string &datacenter) {
    if (datacenter == ANY_DATACENTER)
        return drogon::orm::Criteria();
    return drogon::orm::Criteria(mappers::TrivialJobModel::Cols::_location_id,
                                 drogon::orm::CompareOperator::EQ, datacenter);
}

const auto GET_SUMMARIES_SQL = R"(
    SELECT
        i.id AS impact_id,
        i.carbon_intensity,
        i.total_emissions,
        i.total_electricity,
        MIN(j.time_stamp) AS start_time,
        MAX(j.time_stamp) AS end_time,
        array_agg(DISTINCT j.location_id) AS locations,
        SUM(j.additional_load) AS total_load,
        COUNT(j.id) AS block_count
    FROM impacts i
    LEFT JOIN jobs j ON i.id = j.impact_id
    GROUP BY i.id
)"s;

const auto GET_TRIVIAL_IMPACTS_SQL = R"(
    SELECT
        impact_id,
        carbon_intensity,
        total_emissions,
        total_electricity
    FROM trivial_impacts
)"s;

} // namespace

auto add(const SchedulerOutput &output) -> drogon::Task<string> {
    auto transaction =
        co_await drogon::app().getDbClient()->newTransactionCoro();
    Context context(transaction);

    auto impactModel = mappers::toDto(output.impact);
    impactModel = co_await context.impactMapper.insert(impactModel);
    const auto impactId = impactModel.getValueOfId();

    for (auto &&jobModel :
         output.blocks |
             views::transform(mappers::toDto.withImpactId(impactId))) {
        co_await context.jobsMapper.insert(jobModel);
    }

    co_return scheduler::utils::parseIntToStringID(impactId);
}

auto addTrivial(const SchedulerOutput &output, const string &scheduleIdString)
    -> drogon::Task<void> {
    auto transaction =
        co_await drogon::app().getDbClient()->newTransactionCoro();
    Context context(transaction);

    const auto impactId =
        scheduler::utils::parseStringIDtoInt(scheduleIdString);

    auto trivialImpactModel =
        mappers::toTrivialDto.withImpactId(impactId)(output.impact);
    trivialImpactModel =
        co_await context.trivialImpactMapper.insert(trivialImpactModel);
    const auto trivialImpactId = trivialImpactModel.getValueOfId();

    for (auto &&trivialJobModel :
         output.blocks |
             views::transform(
                 mappers::toTrivialDto.withTrivialImpactId(trivialImpactId))) {
        co_await context.trivialJobsMapper.insert(trivialJobModel);
    }
}

auto get(const string &scheduleIdString, const string &datacenter)
    -> drogon::Task<ScheduleResult> {
    auto context = getContext();

    const int jobIdInt = scheduler::utils::parseStringIDtoInt(scheduleIdString);

    try {
        const auto fullCriteria =
            combineCriteria(jobImpactIdEqualityCriteria(jobIdInt),
                            specificDatacenterCriteria(datacenter));

        auto [impactModel, jobsModels] = co_await scheduler::coro::when_all(
            to_task<mappers::ImpactModel>(
                context.impactMapper.findByPrimaryKey(jobIdInt)),
            to_task<vector<mappers::JobModel>>(
                context.jobsMapper.findBy(fullCriteria)));

        co_return ScheduleResult{.scheduleId = scheduleIdString,
                                 .schedule = mappers::fromDtoAll(jobsModels),
                                 .impact = mappers::fromDto(impactModel)};
    } catch (const exception &e) {
        LOG_ERROR << "NO scheduled job with id=" + scheduleIdString
                  << " in the DB!";
        throw scheduler::exceptions::ValidationException(
            "No scheduled job with id: " + scheduleIdString);
    }
}

auto getTrivial(const string &scheduleIdString, const string &datacenter)
    -> drogon::Task<ScheduleResult> {
    auto context = getContext();

    const int jobIdInt = scheduler::utils::parseStringIDtoInt(scheduleIdString);

    try {
        const auto impactCriteria =
            drogon::orm::Criteria(mappers::TrivialImpactModel::Cols::_impact_id,
                                  drogon::orm::CompareOperator::EQ, jobIdInt);

        auto trivialImpactModels =
            co_await context.trivialImpactMapper.findBy(impactCriteria);
        if (trivialImpactModels.empty()) {
            throw scheduler::exceptions::SchedulingException(
                "No trivial scheduled job with id: " + scheduleIdString);
        }
        auto impactModel = trivialImpactModels.front();
        const int trivialImpactId = impactModel.getValueOfId();

        const auto fullCriteria =
            combineCriteria(trivialJobImpactIdEqualityCriteria(trivialImpactId),
                            specificTrivialDatacenterCriteria(datacenter));

        auto jobsModels =
            co_await context.trivialJobsMapper.findBy(fullCriteria);

        co_return ScheduleResult{
            .scheduleId = scheduleIdString,
            .schedule = mappers::fromTrivialDtoAll(jobsModels, jobIdInt),
            .impact = mappers::fromDto(impactModel)};
    } catch (const scheduler::exceptions::SchedulingException &) {
        throw;
    } catch (const exception &e) {
        LOG_ERROR << "Error fetching trivial schedule with id=" +
                         scheduleIdString;
        throw scheduler::exceptions::SchedulingException(
            "No trivial scheduled job with id: " + scheduleIdString);
    }
}

auto get(time_point start, time_point end, const string &datacenter)
    -> drogon::Task<vector<ScheduleBlock>> {
    auto context = getContext();

    const auto fullCriteria =
        combineCriteria(jobTimestampAfterStartCriteria(start),
                        jobTimestampBeforeEndCriteria(end),
                        specificDatacenterCriteria(datacenter));

    co_return mappers::fromDtoAll(
        co_await context.jobsMapper.findBy(fullCriteria));
}

auto scheduleSummaries() -> drogon::Task<vector<ScheduleSummary>> {
    auto db = drogon::app().getDbClient();
    // TODO: fix when_all and use when_all here
    // right now we can't due to when_all structured binding bug and
    // the fact that it only takes drogon::Task (these are SqlAwaiters)
    auto res = co_await db->execSqlCoro(GET_SUMMARIES_SQL);
    auto trivialRes = co_await db->execSqlCoro(GET_TRIVIAL_IMPACTS_SQL);

    auto trivialMap = unordered_map<int, ScheduleImpact>{};
    for (const auto &row : trivialRes) {
        trivialMap[row["impact_id"].as<int>()] = {
            .carbon_intensity = row["carbon_intensity"].as<double>(),
            .total_emissions = row["total_emissions"].as<double>(),
            .total_electricity = row["total_electricity"].as<double>()};
    }

    auto scheduleSummaries = vector<ScheduleSummary>{};
    scheduleSummaries.reserve(res.size());
    for (const auto &row : res) {
        const auto impactId = row["impact_id"].as<int>();

        // TODO: there are some fishy string manipulations here (needs clean)
        auto locStr = row["locations"].as<string>();
        // strip '{' and '}'
        if (locStr.length() >= 2)
            locStr = locStr.substr(1, locStr.length() - 2);
        auto locations = vector<string>{};
        if (!locStr.empty()) {
            stringstream ss(locStr);
            string item;
            while (getline(ss, item, ',')) {
                // If the strings are quoted, we might need to unquote them
                if (item.front() == '"' && item.back() == '"')
                    item = item.substr(1, item.length() - 2);
                locations.push_back(item);
            }
        }

        auto startTime = string{};
        auto endTime = string{};
        auto totalLoad = 0.;
        auto blockCount = 0;

        if (!row["start_time"].isNull()) {
            auto sd = trantor::Date::fromDbStringLocal(
                row["start_time"].as<string>());
            startTime = scheduler::utils::toIso8601(
                scheduler::utils::trantorToChrono(sd));
        }
        if (!row["end_time"].isNull()) {
            auto ed =
                trantor::Date::fromDbStringLocal(row["end_time"].as<string>());
            // add 5 minutes to end time since it represents the start of the
            // last block
            ed = ed.after(5 * 60);
            endTime = scheduler::utils::toIso8601(
                scheduler::utils::trantorToChrono(ed));
        }
        if (!row["total_load"].isNull())
            totalLoad = row["total_load"].as<double>();
        if (!row["block_count"].isNull())
            blockCount = row["block_count"].as<int>();

        auto summary = ScheduleSummary{
            .scheduleId = scheduler::utils::parseIntToStringID(impactId),
            .impact = {.carbon_intensity = row["carbon_intensity"].as<double>(),
                       .total_emissions = row["total_emissions"].as<double>(),
                       .total_electricity =
                           row["total_electricity"].as<double>()},
            .trivialImpact = {},
            .startTime = startTime,
            .endTime = endTime,
            .locations = locations,
            .totalLoad = totalLoad,
            .blockCount = blockCount};

        if (trivialMap.contains(impactId))
            summary.trivialImpact = trivialMap[impactId];

        scheduleSummaries.push_back(std::move(summary));
    }
    co_return scheduleSummaries;
}

auto deleteSchedule(const string &scheduleId) -> drogon::Task<> {
    auto context = getContext();
    co_await context.impactMapper.deleteByPrimaryKey(
        scheduler::utils::parseStringIDtoInt(scheduleId));
    // we have cascade on delete, so no need to delete the children manually
}

} // namespace scheduler::calendar
