#include "Scheduler.hpp"
#include "SchedulerAlgo.hpp"
#include "structs/JobRequest.hpp"
#include "utils/TimeGridder.hpp"
#include <vector>

namespace scheduler {

using namespace std;
using namespace drogon;
using namespace scheduler::exceptions;

constexpr double EPSILON = 1e-6;

auto Scheduler::doScheduleJob(JobRequest job) -> drogon::Task<SchedulerOutput> {
    auto data = co_await fetch_data(job);
    const auto n_intervals = data.n_intervals;
    auto costs_f = data.generate_cost_functions();

    // calculate
    auto [min_cost, optimal_schedule] =
        calc_multiple(data.loads_f, data.capacities_f, costs_f,
                      data.penalties_f, job.workload_amount);

    auto total_emissions = 0.0;      // gCO2eq
    auto total_energy = 0.0;         // kWh
    auto carbon_intensity_sum = 0.0; // to average CI across all blocks
    auto blocks_count = 0;
    auto blocks = vector<InternalBlock>{};

    const auto index_to_time = [&](const int64_t i)
        -> decltype(scheduler::TIME_GRIDDER)::time_point_t {
        return scheduler::TIME_GRIDDER.toTimePoint(i + data.time_index_offset);
    };

    for (size_t i = 0; i < optimal_schedule.size(); ++i) {
        const auto &loc_id = data.location_ids[i];
        const auto &schedule_vec = optimal_schedule[i];
        const auto &ci_vec = data.carbon_intensities_f[i];
        const auto efficiency = data.kwh_per_flo[i];

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

            total_energy += load * efficiency;
            total_emissions += load * efficiency * ci_vec[j];
            carbon_intensity_sum += ci_vec[j];
        }
    }

    co_return {
        .blocks = std::move(blocks),
        .impact = {
            // TODO: does this way of averaging even make sense?
            .carbon_intensity =
                blocks_count > 0 ? carbon_intensity_sum / blocks_count : 0.,
            .total_emissions = total_emissions,
            .sci = total_energy > 0.0 ? total_emissions / total_energy : 0.,
        }};
}

} // namespace scheduler
