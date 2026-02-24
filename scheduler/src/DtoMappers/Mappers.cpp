#include "utils/Utils.hpp"
#include <DtoMappers/Mappers.h>
#include <models/Impacts.h>
#include <models/Jobs.h>
#include <models/TrivialImpacts.h>
#include <models/TrivialJobs.h>
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

auto f_toTrivialDto(const scheduler::ScheduleImpact &impact, int impactId) -> TrivialImpactModel {
    TrivialImpactModel impactDB;
    impactDB.setImpactId(impactId);
    impactDB.setCarbonIntensity(impact.carbon_intensity);
    impactDB.setSci(impact.sci);
    impactDB.setTotalEmissions(impact.total_emissions);
    return impactDB;
}

auto f_toTrivialDto(const scheduler::InternalBlock &block, int trivialImpactId) -> TrivialJobModel {
    TrivialJobModel job;
    job.setAdditionalLoad(block.additionalLoad);
    job.setLocationId(block.location);
    job.setTrivialImpactId(trivialImpactId);
    job.setTimeStamp(scheduler::utils::chronoToTrantor(block.timestamp));
    return job;
}

auto f_fromDto(const TrivialImpactModel &impactDto) -> scheduler::ScheduleImpact {
    return {.carbon_intensity = impactDto.getValueOfCarbonIntensity(),
            .total_emissions = impactDto.getValueOfTotalEmissions(),
            .sci = impactDto.getValueOfSci()};
}

auto f_fromDto(const TrivialJobModel &jobDto, int impactId) -> scheduler::ScheduleBlock {
    auto chronoTimestamp =
        scheduler::utils::trantorToChrono(jobDto.getValueOfTimeStamp());
    auto stringId =
        scheduler::utils::parseIntToStringID(impactId);
    return ScheduleBlock{.timestamp = chronoTimestamp,
                         .scheduleId = stringId,
                         .location = jobDto.getValueOfLocationId(),
                         .additionalLoad = jobDto.getValueOfAdditionalLoad()};
}

} // namespace scheduler::mappers
