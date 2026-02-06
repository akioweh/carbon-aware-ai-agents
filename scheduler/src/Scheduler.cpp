#include "Scheduler.hpp"
#include "Calendar.hpp"
#include "SchedulerAlgo.hpp"
#include "StatsAPIClient.hpp"
#include "structs/JobRequest.hpp"
#include "utils/Coro.hpp"
#include <vector>

using namespace std;
using namespace drogon;
using namespace scheduler;
using namespace scheduler::exceptions;

auto Scheduler::scheduleJob(JobRequest job) -> Task<SchedulerOutput> {
    // JobRequest deserialization validates these, but just in case
    assert(job.workload_amount >= 0.);
    assert(job.earliest_start <= job.latest_finish);

    const auto time_window_start =
        max(std::chrono::system_clock::now(), job.earliest_start);
    const auto time_window_end = job.latest_finish;

    if (time_window_end <= time_window_start)
        throw SchedulingException(
            "Effective scheduling window is empty: latest_finish is in "
            "the past or too close to the current time");

    const auto total_minutes = chrono::duration_cast<chrono::minutes>(
                                   time_window_end - time_window_start)
                                   .count();
    const auto n_intervals = total_minutes / 5; // 5 minute intervals

    if (n_intervals <= 0)
        throw SchedulingException(
            "Scheduling window too narrow: must span at least one "
            "5-minute interval");

    // fetch data
    const auto [locations, existing_schedule] = co_await coro::when_all(
        stats_api.getAllDatacenters(),
        calendar::get(time_window_start, time_window_end));
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
            if (tp.timestamp < time_window_start ||
                tp.timestamp >= time_window_end)
                continue;
            const auto index = chrono::duration_cast<chrono::minutes>(
                                   tp.timestamp - time_window_start)
                                   .count() /
                               5;
            load[index] = tp.predictedLoad;
            greenness[index] = tp.predictedGreenness;
        }
        greennesses.push_back(std::move(greenness));
        loads_f.push_back(std::move(load));
        costs_f.emplace_back(capacities_f.back(), greennesses.back());
    }
    // add loads from existing schedule
    for (const auto &block : existing_schedule) {
        assert(block.timestamp >= time_window_start &&
               block.timestamp < time_window_end);
        auto loc_it = ranges::find(location_ids, block.location);
        if (loc_it == location_ids.end())
            continue;
        const auto loc_index = distance(location_ids.begin(), loc_it);
        const auto time_index = chrono::duration_cast<chrono::minutes>(
                                    block.timestamp - time_window_start)
                                    .count() /
                                5;
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
                .timestamp = time_window_start + chrono::minutes(j * 5),
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
