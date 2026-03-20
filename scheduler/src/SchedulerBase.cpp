#include "SchedulerBase.hpp"
#include "Calendar.hpp"
#include "exceptions/SchedulingException.hpp"
#include "utils/Coro.hpp"
#include <ranges>

namespace scheduler {

using namespace std;
using namespace drogon;
using namespace scheduler::exceptions;

/**
 * This method assumes already-validated job request parameters!
 *
 * Throws SchedulingException if there are no available data centers (sources).
 */
auto SchedulerBase::fetch_data(const JobRequest &job)
    -> drogon::Task<SchedulerData> {
    assert(job.workload_amount >= 0.);
    assert(job.earliest_start <= job.latest_finish);

    const auto time_index_offset = TIME_GRIDDER.toIndex(job.earliest_start);

    const auto time_to_index =
        [&](const decltype(TIME_GRIDDER)::time_point_t &tp) -> int64_t {
        return TIME_GRIDDER.toIndex(tp) - time_index_offset;
    };
    const auto index_to_time =
        [&](const int64_t i) -> decltype(TIME_GRIDDER)::time_point_t {
        return TIME_GRIDDER.toTimePoint(i + time_index_offset);
    };

    const auto n_intervals =
        TIME_GRIDDER.toIndexCeil(job.latest_finish) - time_index_offset + 1;

    const auto time_start = index_to_time(0);
    const auto time_end = index_to_time(n_intervals);

    const auto [locations, existing_schedule] = co_await coro::when_all(
        stats_api.getAllDatacenters(job.preferred_datacenter),
        calendar::get(time_start, time_end));
    const auto n_locations = locations.size();

    auto data = SchedulerData{};
    data.n_intervals = n_intervals;
    data.time_index_offset = time_index_offset;
    data.location_ids.reserve(n_locations);
    data.loads_f.reserve(n_locations);
    data.capacities_f.reserve(n_locations);
    data.carbon_intensities_f.reserve(n_locations);
    data.kwh_per_flo.reserve(n_locations);

    for (const auto &loc : locations) {
        data.location_ids.push_back(loc.id);

        // HACK: placeholder dummy value for hardware specification
        const auto kwh_per_flo = job.kwh_per_flo;
        data.kwh_per_flo.push_back(kwh_per_flo);

        auto load = vector(n_intervals, 0.);
        auto capacity = vector(n_intervals, 0.);
        auto carbon_intensity = vector(n_intervals, 0.);
        for (const auto &tp : loc.timeSeries) {
            const auto index = time_to_index(tp.timestamp);
            if (index < 0 || index >= n_intervals)
                continue;
            load[index] = tp.load;
            capacity[index] = tp.capacity;
            carbon_intensity[index] = tp.carbon_intensity;
        }
        data.loads_f.push_back(std::move(load));
        data.capacities_f.push_back(std::move(capacity));
        data.carbon_intensities_f.push_back(std::move(carbon_intensity));
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

    // HACK: we're hijacking the load and capacity vectors to enforce the
    // max_load constraint from the job request... as existing loads are
    // "discarded", we effectively schedule on a "clean" calendar
    for (const auto i : std::views::iota(0UZ, n_locations)) {
        for (const auto j : std::views::iota(int64_t{}, n_intervals)) {
            const auto remaining = data.capacities_f[i][j] - data.loads_f[i][j];
            data.loads_f[i][j] = job.max_load - min(remaining, job.max_load);
            data.capacities_f[i][j] =
                min(data.capacities_f[i][j], job.max_load);
        }
    }

    data.penalties_f = vector(data.location_ids.size(), job.startup_overhead);

    if (data.location_ids.empty())
        throw exceptions::SchedulingException(
            "No data center locations available for scheduling");

    co_return data;
}

// note that this method itself is NOT a coroutine;
// we eagerly validate (and reject) the job request eventhough
// the actual scheduler logic may run later depending on the queue
auto SchedulerBase::scheduleJob(JobRequest job)
    -> drogon::Task<SchedulerOutput> {
    if (job.workload_amount < 0.)
        throw scheduler::exceptions::ValidationException(
            "workload_amount cannot be negative");
    if (job.latest_finish < job.earliest_start)
        throw scheduler::exceptions::ValidationException(
            "latest_finish must be after earliest_start");

    // more thourough time gridder window size checking
    if (scheduler::TIME_GRIDDER.toIndex(job.latest_finish) <=
        scheduler::TIME_GRIDDER.toIndex(job.earliest_start)) {
        throw scheduler::exceptions::SchedulingException(
            "Time window too narrow");
    }

    return doScheduleJob(std::move(job));
}

} // namespace scheduler
