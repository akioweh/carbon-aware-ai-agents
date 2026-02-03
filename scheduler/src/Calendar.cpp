#include "structs/ScheduleBlock.hpp"
#include <Calendar.hpp>
#include <DtoMappers/Mappers.h>
#include <Scheduler.hpp>
#include <drogon/orm/Exception.h>
#include <ranges>
#include <utils/Coro.hpp>
#include <utils/Utils.hpp>

namespace calendarService {

namespace {

struct Context {
    mappers::ImpactMapper impactMapper;
    mappers::JobMapper jobsMapper;
    explicit Context(const drogon::orm::DbClientPtr &db)
        : impactMapper(db), jobsMapper(db) {}
};

auto getContex() { return Context(drogon::app().getDbClient()); }

auto jobImpactIdEqualityCriteria(const int impactId) {
    return drogon::orm::Criteria(mappers::JobModel::Cols::_impact_id,
                                 drogon::orm::CompareOperator::EQ, impactId);
}

// I will add criteria for the timestamps here

} // namespace

auto add(Schedule schedule) -> drogon::Task<> {
    auto transaction = co_await drogon::app().getDbClient()->newTransactionCoro();
    Context context(transaction) ;
    const auto &[impact, intervals] = schedule;

    auto impactModel = mappers::toDto(impact);
    co_await context.impactMapper.insert(impactModel);
    const int impactId = impactModel.getValueOfId();

    for (auto &&jobModel :
         intervals |
             std::views::transform(mappers::toDto.withImpactId(impactId))) {
        co_await context.jobsMapper.insert(jobModel);
    }
}

auto get(const std::string &jobIdString) -> drogon::Task<ScheduleResult> {
    auto context = getContex() ;

    const int jobIdInt = scheduler::utils::parseStringIDtoInt(jobIdString);

    auto [impactModel, jobsModels] = co_await scheduler::coro::when_all(
        to_task<mappers::ImpactModel>(context.impactMapper.findByPrimaryKey(jobIdInt)),
        to_task<std::vector<mappers::JobModel>>(
            context.jobsMapper.findBy(jobImpactIdEqualityCriteria(jobIdInt))));

    auto impact = mappers::fromDto(impactModel);
    auto jobs = mappers::fromDtoAll(jobsModels);

    co_return ScheduleResult{
        .jobId = jobIdString, .schedule = jobs, .impact = impact};
}

auto get() -> drogon::Task<Calendar> {
    auto context = getContex();

    auto [impactDtos, allJobsDtos] = co_await scheduler::coro::when_all(
        to_task<std::vector<mappers::ImpactModel>>(context.impactMapper.findAll()),
        to_task<std::vector<mappers::JobModel>>(context.jobsMapper.findAll()));

    Calendar calendar;

    for (const auto &impactDto : impactDtos) {
        auto impact = mappers::fromDto(impactDto);
        calendar[scheduler::utils::parseIntToStringID(impactDto.getValueOfId())]
            .first = impact;
    }

    for (const auto &job :
         allJobsDtos | std::views::transform(mappers::fromDto)) {
        calendar[job.jobId].second.insert(job);
    }

    co_return calendar;
}

auto deleteSchedule(const std::string &jobId) -> drogon::Task<> {
    auto context = getContex();
    co_await context.impactMapper.deleteByPrimaryKey(
        scheduler::utils::parseStringIDtoInt(jobId));
    // we have cascade on delete, so no need to delete the children manually
}

} // namespace calendarService