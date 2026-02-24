#include "TrivialScheduler.hpp"
#include "Calendar.hpp"
#include "StatsAPIClient.hpp"
#include "structs/JobRequest.hpp"
#include "exceptions/SchedulingException.hpp"
#include "utils/Coro.hpp"
#include "utils/TimeGridder.hpp"
#include <chrono>
#include <vector>

using namespace std;
using namespace drogon;
using namespace scheduler;
using namespace scheduler::exceptions;

using FiveMinutes =
    std::chrono::duration<int, ratio<300>>; // 5 minutes in seconds

constexpr auto time_gridder = scheduler::utils::TimeGridder<FiveMinutes>{};

struct LocationCost {
    std::vector<double> &capacities;
    std::vector<double> &greenness_scores;

    auto operator[](int i) const {
        const auto g = greenness_scores.at(i);
        const auto c = capacities.at(i);
        return [g, c](double load) -> double {
            // cost increases with load and decreases with greenness.
            // 0.01 to avoid div by zero
            return load / c / std::max(g, 0.01);
        };
    }
};

auto TrivialScheduler::scheduleJob(JobRequest job) -> Task<SchedulerOutput> {
    assert(job.workload_amount >= 0.);
    assert(job.earliest_start <= job.latest_finish);

    const auto time_index_offset = time_gridder.toIndex(job.earliest_start);
    const auto time_to_index =
        [&](const decltype(time_gridder)::time_point_t &tp) -> long long {
        return time_gridder.toIndex(tp) - time_index_offset;
    };
    const auto index_to_time =
        [&](const long long i) -> decltype(time_gridder)::time_point_t {
        return time_gridder.toTimePoint(i + time_index_offset);
    };

    const auto n_intervals =
        time_gridder.toIndexCeil(job.latest_finish) - time_index_offset;
    const auto time_start = index_to_time(0);
    const auto time_end = index_to_time(n_intervals);

    const auto &&[locations, existing_schedule] = co_await coro::when_all(
        stats_api.getAllDatacenters(), calendar::get(time_start, time_end));
    const auto n_locations = locations.size();

    auto location_ids = vector<string>();
    auto loads_f = vector<vector<double>>();
    auto capacities_f = vector<vector<double>>();
    auto costs_f = vector<LocationCost>();
    auto greennesses = vector<vector<double>>();
    location_ids.reserve(n_locations);
    loads_f.reserve(n_locations);
    capacities_f.reserve(n_locations);
    costs_f.reserve(n_locations);
    greennesses.reserve(n_locations);

    for (const auto &loc : locations) {
        location_ids.push_back(loc.id);
        capacities_f.emplace_back(n_intervals, loc.maxLoad);

        auto load = vector(n_intervals, 0.);
        auto greenness = vector(n_intervals, 1.);
        const auto &data = loc.timeSeries;
        for (const auto &tp : data) {
            if (tp.timestamp < time_start || tp.timestamp >= time_end)
                continue;
            const auto index = time_to_index(tp.timestamp);
            if (index >= 0 && index < n_intervals) {
                load[index] = tp.predictedLoad;
                greenness[index] = tp.predictedGreenness;
            }
        }
        greennesses.push_back(std::move(greenness));
        loads_f.push_back(std::move(load));
        // Note: we need to use references to capacities and greenness inside LocationCost
        // Emplace back on vectors can reallocate and invalidate references. 
        // We'll populate costs_f in a separate loop below after vectors are fully populated.
    }
    
    for (size_t i = 0; i < n_locations; ++i) {
        costs_f.emplace_back(capacities_f[i], greennesses[i]);
    }

    for (const auto &block : existing_schedule) {
        auto loc_it = ranges::find(location_ids, block.location);
        if (loc_it == location_ids.end()) continue;
        const auto loc_index = distance(location_ids.begin(), loc_it);
        const auto time_index = time_to_index(block.timestamp);
        if (time_index >= 0 && time_index < n_intervals) {
            loads_f[loc_index][time_index] += block.additionalLoad;
        }
    }

    auto penalties_f = vector(location_ids.size(), 1.);

    if (location_ids.empty())
        throw SchedulingException("No data center locations available for scheduling");

    // Trivial placement logic without loops that could hang
    vector<vector<double>> res(n_locations, vector<double>(n_intervals, 0.0));
    double rem_work = job.workload_amount;
    
    // Spread evenly across the first available interval for simplicity, just a naive approach
    for (size_t i = 0; i < n_locations && rem_work > 1e-6; ++i) {
        for (long long j = 0; j < n_intervals && rem_work > 1e-6; ++j) {
            double capacity = capacities_f[i][j];
            double existing = loads_f[i][j];
            double available = std::max(0.0, capacity - existing);
            
            if (available > 1e-6) {
                double to_take = std::min(available, rem_work);
                res[i][j] = to_take;
                rem_work -= to_take;
            }
        }
    }

    if (rem_work > 1e-6) {
        throw SchedulingException("Cannot fit trivial schedule inside the window and existing capacities");
    }

    auto total_emissions = 0.0;
    auto total_carbon_intensity_sum = 0.0;
    auto sci = 0.0;
    auto blocks = vector<InternalBlock>{};
    auto blocks_count = 0;

    for (size_t i = 0; i < n_locations; ++i) {
        const auto &loc_id = location_ids[i];
        const auto &schedule_vec = res[i];
        const auto &greenness_vec = costs_f[i].greenness_scores;

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
            sci += costs_f[i][j](loads_f[i][j] + load) - costs_f[i][j](loads_f[i][j]);
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
