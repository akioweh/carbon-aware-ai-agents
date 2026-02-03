#include "utils/Utils.hpp"
#include <DtoMappers/Mappers.h>
#include <Scheduler.hpp>
#include <models/Impacts.h>
#include <models/Jobs.h>
#include <structs/ScheduleBlock.hpp>

namespace mappers {
auto toDto(const ScheduleImpact &impact) -> ImpactModel {
    ImpactModel impactDB;
    impactDB.setCarbonIntensity(impact.carbon_intensity);
    impactDB.setSci(impact.sci);
    impactDB.setTotalEmissions(impact.total_emissions);
    return impactDB;
}

auto toDto(const ScheduleBlock &block, int impactId) -> JobModel {
    JobModel job;
    job.setAdditionalLoad(block.additionalLoad);
    job.setLocationId(block.location);
    job.setImpactId(impactId);
    job.setTimeStamp(scheduler::utils::chronoToTrantor(block.timestamp));
    return job;
}

auto fromDto(const ImpactModel &impactDto) -> ScheduleImpact {
    return {.carbon_intensity = impactDto.getValueOfCarbonIntensity(),
            .total_emissions = impactDto.getValueOfTotalEmissions(),
            .sci = impactDto.getValueOfSci()};
}

auto fromDto(const JobModel &jobDto) -> ScheduleBlock {
    auto chronoTimestamp =
        scheduler::utils::trantorToChrono(jobDto.getValueOfTimeStamp());
    auto stringId =
        scheduler::utils::parseIntToStringID(jobDto.getValueOfImpactId());
    return ScheduleBlock{.timestamp = chronoTimestamp,
                         .jobId = stringId,
                         .location = jobDto.getValueOfLocationId(),
                         .additionalLoad = jobDto.getValueOfAdditionalLoad()};
}

}; // namespace mappers