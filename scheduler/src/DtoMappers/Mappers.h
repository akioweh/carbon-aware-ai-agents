#ifndef MAPPERS
#define MAPPERS

#include "models/Impacts.h"
#include "models/Jobs.h"
#include "structs/ScheduleBlock.hpp"
#include "structs/SchedulerOutput.hpp"
#include <concepts>

namespace scheduler::mappers {
using JobModel = drogon_model::calendar_db::Jobs;
using ImpactModel = drogon_model::calendar_db::Impacts;
using JobMapper = drogon::orm::CoroMapper<JobModel>;
using ImpactMapper = drogon::orm::CoroMapper<ImpactModel>;

auto f_toDto(const scheduler::ScheduleImpact &) -> ImpactModel;
auto f_toDto(const scheduler::InternalBlock &, int) -> JobModel;
auto f_fromDto(const ImpactModel &) -> scheduler::ScheduleImpact;
auto f_fromDto(const JobModel &) -> scheduler::ScheduleBlock;

struct FromDtoFn {
    auto operator()(auto &&dto) const {
        return f_fromDto(std::forward<decltype(dto)>(dto));
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

inline constexpr FromDtoFn fromDto{};
inline constexpr ToDtoFn toDto{};

// Convienience so i dont repeat myself.
template <typename T>
concept MappableModel =
    std::same_as<T, JobModel> || std::same_as<T, ImpactModel>;
template <MappableModel T> auto fromDtoAll(const std::vector<T> &models) {
    return models | std::views::transform(fromDto) |
           std::ranges::to<std::vector>();
}

} // namespace scheduler::mappers
#endif
