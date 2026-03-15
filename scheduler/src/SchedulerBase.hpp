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

struct SchedulerData {
    std::vector<std::string> location_ids;
    std::vector<std::vector<double>> loads_f;
    std::vector<std::vector<double>> capacities_f;
    std::vector<std::vector<double>> carbon_intensities_f;
    std::vector<double> kwh_per_flo;
    std::vector<double> penalties_f; // startup overhead, same units as workload
    int64_t n_intervals;
    int64_t time_index_offset;

    auto generate_cost_functions() -> std::vector<LocationCost> {
        auto res = std::vector<LocationCost>{};
        res.reserve(capacities_f.size());
        for (const auto [carbon_intensity, efficiency] :
             std::views::zip(carbon_intensities_f, kwh_per_flo))
            res.emplace_back(carbon_intensity, efficiency);
        return res;
    }
};

class SchedulerBase {
  protected:
    StatsAPIClient stats_api;

  public:
    virtual ~SchedulerBase() = default;

  protected:
    auto fetch_data(const JobRequest &job) -> drogon::Task<SchedulerData>;
};

} // namespace scheduler

#endif // SCHEDULER_SCHEDULER_BASE_HPP
