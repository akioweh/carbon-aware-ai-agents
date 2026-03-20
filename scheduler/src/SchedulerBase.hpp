#ifndef SCHEDULER_SCHEDULER_BASE_HPP
#define SCHEDULER_SCHEDULER_BASE_HPP
#pragma once

#include "SchedulerAlgo.hpp"
#include "StatsAPIClient.hpp"
#include "structs/JobRequest.hpp"
#include "structs/SchedulerOutput.hpp"
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

/**
 * @class SchedulerBase
 * @brief Abstract base class for schedulers, providing common data fetching and
 * preprocessing logic.
 *
 * Schedulers should inherit from this class and implement the doScheduleJob
 * method following the Non-Virtual Interface pattern.
 */
class SchedulerBase {
  protected:
    StatsAPIClient &stats_api = StatsAPIClient::getInstance();

    auto fetch_data(const JobRequest &job) -> drogon::Task<SchedulerData>;

    virtual auto doScheduleJob(JobRequest job)
        -> drogon::Task<SchedulerOutput> = 0;

  public:
    auto scheduleJob(JobRequest job) -> drogon::Task<SchedulerOutput>;

    virtual ~SchedulerBase() = default;
};

} // namespace scheduler

#endif // SCHEDULER_SCHEDULER_BASE_HPP
