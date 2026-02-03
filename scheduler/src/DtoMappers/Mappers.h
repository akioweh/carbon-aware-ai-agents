#ifndef MAPPERS
#define MAPPERS

#include "structs/ScheduleBlock.hpp"
#include <Scheduler.hpp>
#include <models/Impacts.h>
#include <models/Jobs.h>

namespace mappers {
using JobModel = drogon_model::calendar_db::Jobs;
using ImpactModel = drogon_model::calendar_db::Impacts;
using JobMapper = drogon::orm::Mapper<JobModel>;
using ImpactMapper = drogon::orm::Mapper<ImpactModel>;

auto toDto(ScheduleImpact) -> ImpactModel;

auto toDto(const ScheduleBlock &, int) -> JobModel;

auto fromDto(ImpactModel) -> ScheduleImpact;

auto fromDto(JobModel) -> ScheduleBlock;

}; // namespace mappers

#endif