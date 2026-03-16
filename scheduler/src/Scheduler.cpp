#include "Scheduler.hpp"
#include "SchedulerAlgo.hpp"
#include "structs/JobRequest.hpp"
#include <vector>

namespace scheduler {

using namespace std;
using namespace drogon;
using namespace scheduler::exceptions;

constexpr double EPSILON = 1e-6;

auto Scheduler::scheduleJob(JobRequest job) -> drogon::Task<SchedulerOutput> {
    auto data = co_await fetchAndPrepareData(job);
    const auto n_intervals = data.n_intervals;
    auto costs_f = data.generateCostsF();

    // calculate
    auto [min_cost, optimal_schedule] =
        calc_multiple(data.loads_f, data.capacities_f, costs_f,
                      data.penalties_f, job.workload_amount);

    // transform optimizer output into InternalBlocks + impact metrics
    auto total_emissions = 0.0;
    auto total_carbon_intensity_sum = 0.0;
    auto blocks = vector<InternalBlock>{};
    auto blocks_count = 0;

    const auto index_to_time = [&](const int64_t i)
        -> decltype(scheduler::time_gridder)::time_point_t {
        return scheduler::time_gridder.toTimePoint(i + data.time_index_offset);
    };

    for (size_t i = 0; i < optimal_schedule.size(); ++i) {
        const auto &loc_id = data.location_ids[i];
        const auto &schedule_vec = optimal_schedule[i];
        const auto &sci_vec = data.sci_scores[i];

        for (const auto j : views::iota(int64_t{0}, n_intervals)) {
            const auto load = schedule_vec[j];
            if (load < EPSILON) // filter out negligible loads
                continue;
            blocks.push_back({
                .timestamp = index_to_time(j),
                .location = loc_id,
                .additionalLoad = load,
            });
            ++blocks_count;

            const auto sci = sci_vec[j];
            total_emissions += load * sci;
            total_carbon_intensity_sum += sci;
        }
    }

    co_return {.blocks = std::move(blocks),
               .impact = {
                   .carbon_intensity =
                       blocks_count > 0 ? total_carbon_intensity_sum /
                                              static_cast<double>(blocks_count)
                                        : 0.0,
                   .total_emissions = total_emissions,
                   .sci = min_cost,
               }};
}

} // namespace scheduler
