#ifndef SCHEDULER_SCHEDULER_BASE_HPP
#define SCHEDULER_SCHEDULER_BASE_HPP
#pragma once

#include "SchedulerAlgo.hpp"
#include "StatsAPIClient.hpp"
#include "structs/JobRequest.hpp"
#include "utils/TimeGridder.hpp"
#include <string>
#include <vector>

namespace scheduler {

using FiveMinutes = std::chrono::duration<int, std::ratio<300>>;

inline constexpr auto time_gridder =
    scheduler::utils::TimeGridder<FiveMinutes>{};

struct SchedulerData {
    std::vector<std::string> location_ids;
    std::vector<std::vector<double>> loads_f;
    std::vector<std::vector<double>> capacities_f;
    std::vector<std::vector<double>> greennesses;
    std::vector<double> penalties_f;
    int64_t n_intervals;
    int64_t time_index_offset;

    auto generateCostsF() -> std::vector<LocationCost> {
        std::vector<LocationCost> costs_f;
        costs_f.reserve(capacities_f.size());
        for (size_t i = 0; i < capacities_f.size(); ++i) {
            costs_f.emplace_back(
                LocationCost{.capacities = capacities_f[i],
                             .greenness_scores = greennesses[i]});
        }
        return costs_f;
    }
};

class SchedulerBase {
  protected:
    static constexpr unsigned int KWH = 1000 * 60 * 60;
    StatsAPIClient stats_api;

  public:
    virtual ~SchedulerBase() = default;

  protected:
    auto fetchAndPrepareData(const JobRequest &job)
        -> drogon::Task<SchedulerData>;
};

} // namespace scheduler

#endif // SCHEDULER_SCHEDULER_BASE_HPP
