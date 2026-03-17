#include "TrivialScheduler.hpp"
#include "exceptions/SchedulingException.hpp"
#include "structs/SchedulerOutput.hpp"
#include "utils/TimeGridder.hpp"
#include <algorithm>
#include <numeric>
#include <vector>

namespace scheduler {

using namespace std;
using namespace drogon;
using namespace scheduler::exceptions;

constexpr double EPSILON = 1e-6;
constexpr double MIN_CAPACITY_THRESHOLD = 0.1;
constexpr double TARGET_UTILIZATION = 0.5;

auto TrivialScheduler::scheduleJob(JobRequest job)
    -> drogon::Task<SchedulerOutput> {
    auto data = co_await fetch_data(job);
    const auto n_locations = data.location_ids.size();
    const auto n_intervals = data.n_intervals;
    auto costs_f = data.generate_cost_functions();

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

    // Greedily allocate, starting from the earliest allowed start, using 50%
    // of the available capacity, avoiding <10% total capacity blocks
    for (auto iter_idx = 0UZ; iter_idx < n_locations && rem_work > EPSILON;
         ++iter_idx) {
        const auto i = location_indices[iter_idx];

        // Precompute suffix available capacity to guarantee we never fail if
        // it's possible to fit. Also precompute 50% rule capacity.
        auto suffix_avail = vector(n_intervals + 1, 0.0);
        auto suffix_50_avail = vector(n_intervals + 1, 0.0);
        for (auto j = n_intervals; j--;) {
            const auto capacity = data.capacities_f[i][j];
            const auto existing = data.loads_f[i][j];
            const auto avail = max(0.0, capacity - existing);

            suffix_avail[j] = suffix_avail[j + 1] + avail;

            double rule_avail = 0.0;
            if (avail >= MIN_CAPACITY_THRESHOLD * capacity) {
                rule_avail = TARGET_UTILIZATION * avail;
            }
            suffix_50_avail[j] = suffix_50_avail[j + 1] + rule_avail;
        }

        for (auto j = int64_t{}; j < n_intervals && rem_work > EPSILON; ++j) {
            const auto capacity = data.capacities_f[i][j];
            const auto existing = data.loads_f[i][j];
            const auto available = max(0.0, capacity - existing);

            if (available > EPSILON) {
                // Determine if a penalty applies (new continuous run of work)
                const auto penalty = (j == 0 || res[i][j - 1] < EPSILON)
                                         ? data.penalties_f[i]
                                         : 0.0;

                if (available > penalty + EPSILON) {
                    double ideal_take = 0.0;

                    if (rem_work + penalty > suffix_50_avail[j]) {
                        // Greedily fill all capacity if the 50% rule is
                        // insufficient
                        ideal_take = available;
                    } else if (available >= MIN_CAPACITY_THRESHOLD * capacity) {
                        ideal_take = TARGET_UTILIZATION * available;
                    }

                    const auto must_take =
                        max(0.0, (rem_work + penalty) - suffix_avail[j + 1]);

                    auto to_take = max(ideal_take, must_take);
                    to_take = min(available, to_take);
                    to_take = min(to_take, rem_work + penalty);

                    if (to_take > penalty + EPSILON) {
                        res[i][j] = to_take;
                        rem_work -= (to_take - penalty);
                    }
                }
            }
        }
    }

    if (rem_work > EPSILON) {
        LOG_WARN << "Trivial schedule could not place all work. It will be "
                    "empty. rem_work: "
                 << rem_work;
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
    auto total_sci = 0.0;
    auto total_kwh = 0.0;
    auto blocks = vector<InternalBlock>{};
    auto blocks_count = 0;

    const auto index_to_time = [&](const uint64_t i)
        -> decltype(scheduler::TIME_GRIDDER)::time_point_t {
        return scheduler::TIME_GRIDDER.toTimePoint(i + data.time_index_offset);
    };

    for (size_t i = 0; i < n_locations; ++i) {
        const auto &loc_id = data.location_ids[i];
        const auto &schedule_vec = res[i];
        const auto &sci_vec = data.carbon_intensities_f[i];
        const auto kwh = data.kwh_per_flo[i];

        for (const auto j : views::iota(int64_t{}, n_intervals)) {
            const auto load = schedule_vec[j];
            if (load < EPSILON)
                continue;

            blocks.emplace_back(index_to_time(j), loc_id, load);
            ++blocks_count;

            const auto current_sci = sci_vec[j];
            total_emissions += load * kwh * current_sci;
            total_carbon_intensity_sum += current_sci;
            total_kwh += load * kwh;
            total_sci += costs_f[i][j](data.loads_f[i][j] + load) -
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
                   .sci = (total_kwh > 0.0 ? total_sci / total_kwh : 0.0),
               }};
}

} // namespace scheduler
