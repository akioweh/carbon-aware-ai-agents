#include "TrivialScheduler.hpp"
#include "exceptions/SchedulingException.hpp"
#include <chrono>
#include <vector>

using namespace std;
using namespace drogon;
using namespace scheduler;
using namespace scheduler::exceptions;

auto TrivialScheduler::scheduleJob(JobRequest job) -> Task<SchedulerOutput> {
    auto data = co_await fetchAndPrepareData(job);
    const auto n_locations = data.location_ids.size();
    const auto n_intervals = data.n_intervals;
    auto costs_f = data.generateCostsF();

    // Trivial placement logic without loops that could hang
    vector<vector<double>> res(n_locations, vector<double>(n_intervals, 0.0));
    double rem_work = job.workload_amount;
    
    // Spread evenly across the first available interval for simplicity, just a naive approach
    for (size_t i = 0; i < n_locations && rem_work > 1e-6; ++i) {
        for (long long j = 0; j < n_intervals && rem_work > 1e-6; ++j) {
            double capacity = data.capacities_f[i][j];
            double existing = data.loads_f[i][j];
            double available = std::max(0.0, capacity - existing);
            
            if (available > 1e-6) {
                double to_take = std::min(available, rem_work);
                res[i][j] = to_take;
                rem_work -= to_take;
            }
        }
    }

    if (rem_work > 1e-6) {
        LOG_WARN << "Trivial schedule could not place all work. It will be empty.";
        // We just return an empty schedule, the UI handles missing unoptimized result gracefully
        co_return SchedulerOutput{
            .blocks = {},
            .impact = {0.0, 0.0, 0.0}
        };
    }

    auto total_emissions = 0.0;
    auto total_carbon_intensity_sum = 0.0;
    auto sci = 0.0;
    auto blocks = vector<InternalBlock>{};
    auto blocks_count = 0;

    const auto index_to_time =
        [&](const long long i) -> decltype(scheduler::time_gridder)::time_point_t {
        return scheduler::time_gridder.toTimePoint(i + data.time_index_offset);
    };

    for (size_t i = 0; i < n_locations; ++i) {
        const auto &loc_id = data.location_ids[i];
        const auto &schedule_vec = res[i];
        const auto &greenness_vec = data.greennesses[i];

        for (const auto j : views::iota(0LL, n_intervals)) {
            const auto load = schedule_vec[j];
            if (load < 1e-6) continue;
            
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
            sci += costs_f[i][j](data.loads_f[i][j] + load) - costs_f[i][j](data.loads_f[i][j]);
        }
    }

    co_return {
        .blocks = std::move(blocks),
        .impact = {
            .carbon_intensity = blocks_count > 0 ? total_carbon_intensity_sum / blocks_count : 0.0,
            .total_emissions = total_emissions,
            .sci = sci,
        }
    };
}
