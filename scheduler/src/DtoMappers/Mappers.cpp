#include "DtoMappers/Mappers.h"
#include "structs/ScheduleBlock.hpp"
#include "structs/ScheduleResult.hpp"
#include "structs/SchedulerOutput.hpp"
#include "utils/Utils.hpp"

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
    job.setTimeStamp(utils::chronoToTrantor(block.timestamp));
    return job;
}

auto f_fromDto(const ImpactModel &impactDto) -> ScheduleImpact {
    return {.carbon_intensity = impactDto.getValueOfCarbonIntensity(),
            .total_emissions = impactDto.getValueOfTotalEmissions(),
            .sci = impactDto.getValueOfSci()};
}

auto f_fromDto(const JobModel &jobDto) -> ScheduleBlock {
    auto chronoTimestamp = utils::trantorToChrono(jobDto.getValueOfTimeStamp());
    auto stringId = utils::parseIntToStringID(jobDto.getValueOfImpactId());
    return ScheduleBlock{.timestamp = chronoTimestamp,
                         .scheduleId = stringId,
                         .location = jobDto.getValueOfLocationId(),
                         .additionalLoad = jobDto.getValueOfAdditionalLoad()};
}

auto f_toTrivialDto(const ScheduleImpact &impact, int impactId)
    -> TrivialImpactModel {
    TrivialImpactModel impactDB;
    impactDB.setImpactId(impactId);
    impactDB.setCarbonIntensity(impact.carbon_intensity);
    impactDB.setSci(impact.sci);
    impactDB.setTotalEmissions(impact.total_emissions);
    return impactDB;
}

auto f_toTrivialDto(const InternalBlock &block, int trivialImpactId)
    -> TrivialJobModel {
    TrivialJobModel job;
    job.setAdditionalLoad(block.additionalLoad);
    job.setLocationId(block.location);
    job.setTrivialImpactId(trivialImpactId);
    job.setTimeStamp(utils::chronoToTrantor(block.timestamp));
    return job;
}

auto f_fromDto(const TrivialImpactModel &impactDto) -> ScheduleImpact {
    return {.carbon_intensity = impactDto.getValueOfCarbonIntensity(),
            .total_emissions = impactDto.getValueOfTotalEmissions(),
            .sci = impactDto.getValueOfSci()};
}

auto f_fromDto(const TrivialJobModel &jobDto, int impactId) -> ScheduleBlock {
    auto chronoTimestamp = utils::trantorToChrono(jobDto.getValueOfTimeStamp());
    auto stringId = utils::parseIntToStringID(impactId);
    return ScheduleBlock{.timestamp = chronoTimestamp,
                         .scheduleId = stringId,
                         .location = jobDto.getValueOfLocationId(),
                         .additionalLoad = jobDto.getValueOfAdditionalLoad()};
}

} // namespace scheduler::mappers
