    #ifndef MAPPERS
    #define MAPPERS

    #include "structs/ScheduleBlock.hpp"
    #include <Scheduler.hpp>
    #include <concepts>
    #include <models/Impacts.h>
    #include <models/Jobs.h>

    namespace mappers {
    using JobModel = drogon_model::calendar_db::Jobs;
    using ImpactModel = drogon_model::calendar_db::Impacts;
    using JobMapper = drogon::orm::Mapper<JobModel>;
    using ImpactMapper = drogon::orm::Mapper<ImpactModel>;

    auto f_toDto(const ScheduleImpact&) -> ImpactModel;
    auto f_toDto(const ScheduleBlock &, int) -> JobModel;
    auto f_fromDto(const ImpactModel&) -> ScheduleImpact;
    auto f_fromDto(const JobModel&) -> ScheduleBlock;

    struct FromDtoFn {
        auto operator()(auto &&dto) const {
            return f_fromDto(std::forward<decltype(dto)>(dto));
        }
    };

    struct ToDtoFn {
        auto operator()(const ScheduleImpact &impact) const {
            return f_toDto(impact);
        }

        [[nodiscard]] auto withImpactId(int impactId) const {
            return [impactId](const ScheduleBlock &block) {
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

    }; // namespace mappers
    #endif