#ifndef MAPPERS
#define MAPPERS

#include "models/Impacts.h"
#include "models/Jobs.h"
#include "models/TrivialImpacts.h"
#include "models/TrivialJobs.h"
#include "structs/ScheduleBlock.hpp"
#include "structs/SchedulerOutput.hpp"
#include <concepts>

namespace scheduler::mappers {
using JobModel = drogon_model::calendar_db::Jobs;
using ImpactModel = drogon_model::calendar_db::Impacts;
using TrivialJobModel = drogon_model::calendar_db::TrivialJobs;
using TrivialImpactModel = drogon_model::calendar_db::TrivialImpacts;

using JobMapper = drogon::orm::CoroMapper<JobModel>;
using ImpactMapper = drogon::orm::CoroMapper<ImpactModel>;
using TrivialJobMapper = drogon::orm::CoroMapper<TrivialJobModel>;
using TrivialImpactMapper = drogon::orm::CoroMapper<TrivialImpactModel>;

auto f_toDto(const scheduler::ScheduleImpact &) -> ImpactModel;
auto f_toDto(const scheduler::InternalBlock &, int) -> JobModel;
auto f_fromDto(const ImpactModel &) -> scheduler::ScheduleImpact;
auto f_fromDto(const JobModel &) -> scheduler::ScheduleBlock;

auto f_toTrivialDto(const scheduler::ScheduleImpact &, int impactId) -> TrivialImpactModel;
auto f_toTrivialDto(const scheduler::InternalBlock &, int trivialImpactId) -> TrivialJobModel;
auto f_fromDto(const TrivialImpactModel &) -> scheduler::ScheduleImpact;
auto f_fromDto(const TrivialJobModel &, int impactId) -> scheduler::ScheduleBlock;

struct FromDtoFn {
    auto operator()(auto &&dto) const {
        return f_fromDto(std::forward<decltype(dto)>(dto));
    }
    auto withImpactId(int impactId) const {
        return [impactId](const TrivialJobModel &block) {
            return f_fromDto(block, impactId);
        };
    }
};

struct ToDtoFn {
    auto operator()(const scheduler::ScheduleImpact &impact) const {
        return f_toDto(impact);
    }

    [[nodiscard]] auto withImpactId(int impactId) const {
        return [impactId](const scheduler::InternalBlock &block) {
            return f_toDto(block, impactId);
        };
    }
};

struct ToTrivialDtoFn {
    [[nodiscard]] auto withImpactId(int impactId) const {
        return [impactId](const scheduler::ScheduleImpact &impact) {
            return f_toTrivialDto(impact, impactId);
        };
    }
    
    [[nodiscard]] auto withTrivialImpactId(int trivialImpactId) const {
        return [trivialImpactId](const scheduler::InternalBlock &block) {
            return f_toTrivialDto(block, trivialImpactId);
        };
    }
};

inline constexpr FromDtoFn fromDto{};
inline constexpr ToDtoFn toDto{};
inline constexpr ToTrivialDtoFn toTrivialDto{};

// Convienience so i dont repeat myself.
template <typename T>
concept MappableModel =
    std::same_as<T, JobModel> || std::same_as<T, ImpactModel> || std::same_as<T, TrivialJobModel> || std::same_as<T, TrivialImpactModel>;

template <MappableModel T> auto fromDtoAll(const std::vector<T> &models) {
    return models | std::views::transform(fromDto) |
           std::ranges::to<std::vector>();
}

inline auto fromTrivialDtoAll(const std::vector<TrivialJobModel> &models, int impactId) {
    return models | std::views::transform(fromDto.withImpactId(impactId)) | std::ranges::to<std::vector>();
}

} // namespace scheduler::mappers
#endif
