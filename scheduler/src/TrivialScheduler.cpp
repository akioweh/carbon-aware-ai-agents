#include "TrivialScheduler.hpp"
#include "exceptions/SchedulingException.hpp"
#include "structs/SchedulerOutput.hpp"
#include <algorithm>
#include <numeric>
#include <vector>

namespace scheduler {

using namespace std;
using namespace drogon;
using namespace scheduler::exceptions;

constexpr double EPSILON = 1e-6;

auto TrivialScheduler::scheduleJob(
    JobRequest job) // NOLINT(readability-function-cognitive-complexity)
    -> drogon::Task<SchedulerOutput> {
    auto data = co_await fetchAndPrepareData(job);
    const auto n_locations = data.location_ids.size();
    const auto n_intervals = data.n_intervals;
    auto costs_f = data.generateCostsF();

    // Reorder indices based on preferred_datacenter if it exists
    auto location_indices = vector<size_t>(n_locations);
    ranges::iota(location_indices, 0);
    if (job.preferred_datacenter.has_value()) {
        const auto &pref = job.preferred_datacenter.value();
        auto it = ranges::find(data.location_ids, pref);
        if (it != data.location_ids.end()) {
            const auto pref_idx = distance(data.location_ids.begin(), it);
            if (pref_idx)
                swap(location_indices[0], location_indices[pref_idx]);
        }
    }

    auto res = vector(n_locations, vector(n_intervals, 0.0));
    auto rem_work = job.workload_amount;

    // Spread evenly across the available intervals
    for (auto iter_idx = 0UZ; iter_idx < n_locations && rem_work > EPSILON;
         ++iter_idx) {
        const auto i = location_indices[iter_idx];

        // Precompute suffix available capacity to guarantee we never fail if
        // it's possible to fit
        auto suffix_avail = vector(n_intervals + 1, 0.0);
        for (auto j = n_intervals; j--;) {
            const auto avail =
                max(0.0, data.capacities_f[i][j] - data.loads_f[i][j]);
            suffix_avail[j] = suffix_avail[j + 1] + avail;
        }

        for (auto j = 0LL; j < n_intervals && rem_work > EPSILON; ++j) {
            const auto capacity = data.capacities_f[i][j];
            const auto existing = data.loads_f[i][j];
            const auto available = max(0.0, capacity - existing);

            if (available > EPSILON) {
                // Determine if a penalty applies (new continuous run of work)
                const auto penalty = (j == 0 || res[i][j - 1] < EPSILON)
                                         ? data.penalties_f[i]
                                         : 0.0;

                if (available > penalty + EPSILON) {
                    const auto ideal_take =
                        (rem_work / static_cast<double>(n_intervals - j)) +
                        penalty;
                    const auto must_take =
                        max(0.0, (rem_work + penalty) - suffix_avail[j + 1]);

                    auto to_take = max(ideal_take, must_take);
                    to_take = min(available, to_take);
                    to_take = min(to_take, rem_work + penalty);

                    res[i][j] = to_take;
                    rem_work -= (to_take - penalty);
                }
            }
        }
    }

    if (rem_work > EPSILON) {
        LOG_WARN
            << "Trivial schedule could not place all work. It will be empty.";
        /*
         * Note: Mathematically, if the DP optimizer succeeded, the greedy
         * trivial algorithm should also succeed. The greedy algorithm packs
         * work sequentially, incurring at most the same number of penalties
         * as the DP algorithm. Thus, it consumes the same or less capacity
         * overall.
         *
         * If this branch executes, it usually indicates either a bug in the
         * capacity constraint calculations or edge case floating point
         * precision issues. The controller will simply not attach a trivial
         * result.
         */
        throw exceptions::SchedulingException(
            "Cannot fit trivial schedule inside the "
            "window and existing capacities");
    }

    auto total_emissions = 0.0;
    auto total_carbon_intensity_sum = 0.0;
    auto sci = 0.0;
    auto blocks = vector<InternalBlock>{};
    auto blocks_count = 0;

    const auto index_to_time = [&](const long long i)
        -> decltype(scheduler::time_gridder)::time_point_t {
        return scheduler::time_gridder.toTimePoint(i + data.time_index_offset);
    };

    for (size_t i = 0; i < n_locations; ++i) {
        const auto &loc_id = data.location_ids[i];
        const auto &schedule_vec = res[i];
        const auto &greenness_vec = data.greennesses[i];

        for (const auto j : views::iota(0LL, n_intervals)) {
            const auto load = schedule_vec[j];
            if (load < EPSILON)
                continue;

            blocks.push_back({
                .timestamp = index_to_time(j),
                .location = loc_id,
                .additionalLoad = load,
            });
            ++blocks_count;

            const auto g = max(greenness_vec[j], 0.01);
            const auto ci = 1.0 / g;
            total_emissions += load * ci;
            total_carbon_intensity_sum += ci;
            sci += costs_f[i][j](data.loads_f[i][j] + load) -
                   costs_f[i][j](data.loads_f[i][j]);
        }
    }

    co_return {.blocks = std::move(blocks),
               .impact = {
                   .carbon_intensity =
                       blocks_count > 0 ? total_carbon_intensity_sum /
                                              static_cast<double>(blocks_count)
                                        : 0.0,
                   .total_emissions = total_emissions,
                   .sci = sci,
               }};
}

} // namespace scheduler
