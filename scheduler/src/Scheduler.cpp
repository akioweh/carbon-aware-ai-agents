#include "Scheduler.hpp"
#include "SchedulerAlgo.hpp"
#include "structs/JobRequest.hpp"
#include "exceptions/SchedulingException.hpp"
#include <chrono>
#include <vector>

using namespace std;
using namespace drogon;
using namespace scheduler;
using namespace scheduler::exceptions;

auto Scheduler::scheduleJob(JobRequest job) -> Task<SchedulerOutput> {
    auto data = co_await fetchAndPrepareData(job);
    const auto n_intervals = data.n_intervals;
    auto costs_f = data.generateCostsF();

    // calculate
    auto [min_cost, optimal_schedule] = calc_multiple(
        data.loads_f, data.capacities_f, costs_f, data.penalties_f, job.workload_amount);

    // transform optimizer output into InternalBlocks + impact metrics
    auto total_emissions = 0.0;
    auto total_carbon_intensity_sum = 0.0;
    auto blocks = vector<InternalBlock>{};
    auto blocks_count = 0;

    const auto index_to_time =
        [&](const long long i) -> decltype(scheduler::time_gridder)::time_point_t {
        return scheduler::time_gridder.toTimePoint(i + data.time_index_offset);
    };

    for (size_t i = 0; i < optimal_schedule.size(); ++i) {
        const auto &loc_id = data.location_ids[i];
        const auto &schedule_vec = optimal_schedule[i];
        const auto &greenness_vec = data.greennesses[i];

        for (const auto j : views::iota(0LL, n_intervals)) {
            const auto load = schedule_vec[j];
            if (load < 1e-6) // filter out negligible loads
                continue;
            blocks.push_back({
                .timestamp = index_to_time(j),
                .location = loc_id,
                .additionalLoad = load,
            });
            ++blocks_count;

            const auto g = std::max(greenness_vec[j], 0.01);
            const auto ci = 1.0 / g;
            total_emissions += load * ci;
            total_carbon_intensity_sum += ci;
        }
    }

    co_return {
        .blocks = std::move(blocks),
        .impact = {
            .carbon_intensity = blocks_count > 0
                                    ? total_carbon_intensity_sum / blocks_count
                                    : 0.0,
            .total_emissions = total_emissions,
            .sci = min_cost,
        }};
}
