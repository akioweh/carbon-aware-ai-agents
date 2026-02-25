#include "SchedulerBase.hpp"
#include "Calendar.hpp"
#include "exceptions/SchedulingException.hpp"
#include "utils/Coro.hpp"
#include <chrono>

using namespace std;
using namespace drogon;
using namespace scheduler;
using namespace scheduler::exceptions;

auto SchedulerBase::fetchAndPrepareData(const JobRequest &job)
    -> Task<SchedulerData> {
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
    
    if (n_intervals <= 0) {
        throw SchedulingException("Time window too narrow");
    }

    const auto time_start = index_to_time(0);
    const auto time_end = index_to_time(n_intervals);

    const auto &&[locations, existing_schedule] = co_await coro::when_all(
        stats_api.getAllDatacenters(), calendar::get(time_start, time_end));
    const auto n_locations = locations.size();

    SchedulerData data;
    data.n_intervals = n_intervals;
    data.time_index_offset = time_index_offset;
    data.location_ids.reserve(n_locations);
    data.loads_f.reserve(n_locations);
    data.capacities_f.reserve(n_locations);
    data.greennesses.reserve(n_locations);

    for (const auto &loc : locations) {
        data.location_ids.push_back(loc.id);
        data.capacities_f.emplace_back(n_intervals, loc.maxLoad);

        auto load = vector(n_intervals, 0.);
        auto greenness = vector(n_intervals, 1.);
        const auto &ts_data = loc.timeSeries;
        for (const auto &tp : ts_data) {
            if (tp.timestamp < time_start || tp.timestamp >= time_end)
                continue;
            const auto index = time_to_index(tp.timestamp);
            if (index >= 0 && index < n_intervals) {
                load[index] = tp.predictedLoad;
                greenness[index] = tp.predictedGreenness;
            }
        }
        data.greennesses.push_back(std::move(greenness));
        data.loads_f.push_back(std::move(load));
    }
    
    for (const auto &block : existing_schedule) {
        auto loc_it = ranges::find(data.location_ids, block.location);
        if (loc_it == data.location_ids.end())
            continue;
        const auto loc_index = distance(data.location_ids.begin(), loc_it);
        const auto time_index = time_to_index(block.timestamp);
        if (time_index >= 0 && time_index < n_intervals) {
            data.loads_f[loc_index][time_index] += block.additionalLoad;
        }
    }
    
    data.penalties_f = vector(data.location_ids.size(), 1.); 

    if (data.location_ids.empty())
        throw SchedulingException(
            "No data center locations available for scheduling");

    co_return data;
}
