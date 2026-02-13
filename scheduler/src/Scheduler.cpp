#include "Scheduler.hpp"
#include "Calendar.hpp"
#include "SchedulerAlgo.hpp"
#include "StatsAPIClient.hpp"
#include "structs/JobRequest.hpp"
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

auto Scheduler::scheduleJob(JobRequest job) -> Task<SchedulerOutput> {
    // JobRequest deserialization validates these, but just in case
    assert(job.workload_amount >= 0.);
    assert(job.earliest_start <= job.latest_finish);

    // GLOBAL index (since epoch) of earliest_start
    const auto time_index_offset = time_gridder.toIndex(job.earliest_start);

    // LOCAL index (to be used in dp): index(time) - time_index_offset
    const auto time_to_index =
        [&](const decltype(time_gridder)::time_point_t &tp) -> long long {
        return time_gridder.toIndex(tp) - time_index_offset;
    };
    const auto index_to_time =
        [&](const long long i) -> decltype(time_gridder)::time_point_t {
        return time_gridder.toTimePoint(i + time_index_offset);
    };

    assert(time_to_index(job.earliest_start) == 0);
    // index of end time is the number of intervals since start time is index 0
    // we round up (inclusive-exclusive type indexing)
    const auto n_intervals =
        time_gridder.toIndexCeil(job.latest_finish) - time_index_offset;
    assert(n_intervals > 0);
    // real time points aligned to time grid
    // "start" rounds down; "end" rounds up
    const auto time_start = index_to_time(0);
    const auto time_end = index_to_time(n_intervals);
    // sanity check time gridder math
    assert(time_start <= job.earliest_start);
    assert(time_end >= job.latest_finish);
    assert(index_to_time(1) > job.earliest_start);
    assert(index_to_time(n_intervals - 1) < job.latest_finish);

    // fetch data
    const auto &&[locations, existing_schedule] = co_await coro::when_all(
        stats_api.getAllDatacenters(), calendar::get(time_start, time_end));
    const auto n_locations = locations.size();

    // transform data into format for optimizer
    auto location_ids = vector<string>();
    auto loads_f = vector<vector<double>>();
    auto capacities_f = vector<vector<double>>();
    auto costs_f = vector<LocationCost>();
    auto greennesses = vector<vector<double>>(); // owning vecs for CostFunction
    // reserve to prevent reallocation — LocationCost holds references into
    // capacities_f and greennesses, which would dangle on realloc.
    location_ids.reserve(n_locations);
    loads_f.reserve(n_locations);
    capacities_f.reserve(n_locations);
    costs_f.reserve(n_locations);
    greennesses.reserve(n_locations);

    for (const auto &loc : locations) {
        location_ids.push_back(loc.id);

        // right now, capacity is constant across time
        capacities_f.emplace_back(n_intervals, loc.maxLoad);

        auto load = vector(n_intervals, 0.);
        auto greenness = vector(n_intervals, 1.);
        const auto &data = loc.timeSeries;
        for (const auto &tp : data) {
            // TODO: have stats api returns exactly the window we need
            if (tp.timestamp < time_start || tp.timestamp >= time_end)
                continue;
            const auto index = time_to_index(tp.timestamp);
            load[index] = tp.predictedLoad;
            greenness[index] = tp.predictedGreenness;
        }
        greennesses.push_back(std::move(greenness));
        loads_f.push_back(std::move(load));
        costs_f.emplace_back(capacities_f.back(), greennesses.back());
    }
    // add loads from existing schedule
    for (const auto &block : existing_schedule) {
        assert(block.timestamp >= time_start && block.timestamp < time_end);
        auto loc_it = ranges::find(location_ids, block.location);
        if (loc_it == location_ids.end())
            continue;
        const auto loc_index = distance(location_ids.begin(), loc_it);
        const auto time_index = time_to_index(block.timestamp);
        loads_f[loc_index][time_index] += block.additionalLoad;
    }
    auto penalties_f =
        vector(location_ids.size(), 1.); // currently assuming invariant penalty

    if (location_ids.empty())
        throw SchedulingException(
            "No data center locations available for scheduling");

    // calculate
    auto [min_cost, optimal_schedule] = calc_multiple(
        loads_f, capacities_f, costs_f, penalties_f, job.workload_amount);

    // transform optimizer output into InternalBlocks + impact metrics
    auto total_emissions = 0.0;
    auto total_carbon_intensity_sum = 0.0;
    auto blocks = vector<InternalBlock>{};
    auto blocks_count = 0;

    for (size_t i = 0; i < optimal_schedule.size(); ++i) {
        const auto &loc_id = location_ids[i];
        const auto &schedule_vec = optimal_schedule[i];
        const auto &greenness_vec = costs_f[i].greenness_scores;

        for (const auto j : views::iota(0, n_intervals)) {
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
