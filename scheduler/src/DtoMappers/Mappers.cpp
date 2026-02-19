#include "utils/Utils.hpp"
#include <DtoMappers/Mappers.h>
#include <models/Impacts.h>
#include <models/Jobs.h>
#include <structs/ScheduleBlock.hpp>

namespace scheduler::mappers {
using namespace scheduler;

auto f_toDto(const ScheduleImpact &impact) -> ImpactModel {
    ImpactModel impactDB;
    impactDB.setCarbonIntensity(impact.carbon_intensity);
    impactDB.setSci(impact.sci);
    impactDB.setTotalEmissions(impact.total_emissions);
    return impactDB;
}

auto f_toDto(const InternalBlock &block, int impactId) -> JobModel {
    JobModel job;
    job.setAdditionalLoad(block.additionalLoad);
    job.setLocationId(block.location);
    job.setImpactId(impactId);
    job.setTimeStamp(scheduler::utils::chronoToTrantor(block.timestamp));
    return job;
}

auto f_fromDto(const ImpactModel &impactDto) -> ScheduleImpact {
    return {.carbon_intensity = impactDto.getValueOfCarbonIntensity(),
            .total_emissions = impactDto.getValueOfTotalEmissions(),
            .sci = impactDto.getValueOfSci()};
}

auto f_fromDto(const JobModel &jobDto) -> ScheduleBlock {
    auto chronoTimestamp =
        scheduler::utils::trantorToChrono(jobDto.getValueOfTimeStamp());
    auto stringId =
        scheduler::utils::parseIntToStringID(jobDto.getValueOfImpactId());
    return ScheduleBlock{.timestamp = chronoTimestamp,
                         .scheduleId = stringId,
                         .location = jobDto.getValueOfLocationId(),
                         .additionalLoad = jobDto.getValueOfAdditionalLoad()};
}

} // namespace scheduler::mappers
