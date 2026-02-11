#include "structs/ScheduleBlock.hpp"
#include <Calendar.hpp>
#include <Scheduler.hpp>
#include <StatsAPIClient.hpp>
#include <algorithm>
#include <drogon/HttpTypes.h>
#include <map>
#include <set>
#include <structs/JobRequest.hpp>

using namespace std;
using namespace drogon;

struct LoadBlock {
    std::chrono::system_clock::time_point timestamp;
    double load{};
};

auto operator<=>(const LoadBlock &lhs, const LoadBlock &rhs) -> auto {
    return lhs.timestamp <=> rhs.timestamp;
}

// transform from { jobId: {impact, set<ScheduleBlock>} }
// to dense vector (with implicitly continous timestamps) of loadvalues within
// the given interval.
auto flatten_calendar(const vector<ScheduleBlock> &blocks,
                      const chrono::system_clock::time_point start_time,
                      const chrono::system_clock::time_point end_time)
    -> map<std::string, vector<double>> {

    auto tmp_res = map<string, set<LoadBlock>>{};
    for (const auto &block : blocks) {
        tmp_res[block.location].insert(LoadBlock{.timestamp = block.timestamp,
                                                 .load = block.additionalLoad});
    }

    const auto n_intervals =
        chrono::duration_cast<chrono::minutes>(end_time - start_time).count() /
        5;
    auto res = map<string, vector<double>>{};
    for (auto &[location, loadBlocksSet] : tmp_res) {
        res[location].assign(n_intervals, 0.);

        // chunk by same timestamp, summing loads
        auto rn = loadBlocksSet |
                  views::chunk_by([](const auto &a, const auto &b) -> auto {
                      return a.timestamp == b.timestamp;
                  }) |
                  views::transform([](auto chunk) -> auto {
                      double totalLoad = 0.;
                      for (const auto &lb : chunk)
                          totalLoad += lb.load;
                      return LoadBlock{.timestamp = chunk.front().timestamp,
                                       .load = totalLoad};
                  });
        for (const auto &lb : rn) {
            const auto index = chrono::duration_cast<chrono::minutes>(
                                   lb.timestamp - start_time)
                                   .count() /
                               5;
            res[location].at(index) = lb.load;
        }
    }

    return res;
}

auto dp1(const vector<double> &load, const double max_load,
         const double tot_work) -> auto {
    // do some dp to calculate, for all work amounts in [0, tot_work],
    // the best (minimum impact) schedule to achieve that work

    return vector(max_load + 1, 0.);
}

auto Scheduler::scheduleJob(JobRequest job) -> Task<ScheduleResult> {
    const auto time_window_start =
        max(std::chrono::system_clock::now(), job.earliest_start);
    const auto time_window_end = job.latest_finish;
    auto datacenter_loads = flatten_calendar(
        co_await calendarService::get(time_window_start, time_window_end),
        time_window_start, time_window_end);

    // call dp1 in parallel for each location
    // then, merge results using mega dp (multiple-choice knapsack)

    // TODO
    co_return ScheduleResult{};
}
