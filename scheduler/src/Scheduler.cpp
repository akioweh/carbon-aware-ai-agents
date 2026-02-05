#include "structs/ScheduleBlock.hpp"
#include <Calendar.hpp>
#include <Scheduler.hpp>
#include <StatsAPIClient.hpp>
#include <algorithm>
#include <cmath>
#include <drogon/HttpTypes.h>
#include <execution>
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

template <typename T, typename Func>
concept CostFunction = requires(Func &f, int i, T load) {
    { f[i](load) } -> std::convertible_to<double>;
};

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

/*
 * Algorithmic Analysis:
 *
 * Given is a sequence of n blocks numbered 1 to n;
 * each block_i is associated with an existing_load l_i and max_load r_i.
 * Also given is total work W to be allocated over the blocks.
 * Each block_i has a non-decreasing cost function c_i(load).
 *
 * The optimization problem is to distribute the work W over the blocks into
 * w_1, w_2, ..., w_n such that sum(w_i) >= W, w_i + l_i <= r_i, and the total
 * additional cost incurred, sum(c_i(l_i + w_i) - c_i(l_i)), is minimized.
 * There is also an additional penalty for non-continuous allocations: for each
 * i where w_i > 0 and w_{i-1} == 0, an additional penalty work P must be added
 * to W: sum(w_i) >= W + k * P, where k is the number of such i.
 *
 * The goal is to compute an optimal allocation {w_i} for all W in [0, maxW].
 *
 * At this point, the problem is well-defined, but there remains one very
 * important distinction: are l_i, r_i, W, P continuous or discrete values?
 * If discrete, we can use DP techniques... if continuous, we'd be fucked.
 * Conclusion: the values are discrete, due to algorithmic difficulties :))
 *
 * Without the penalty for non-continuous allocations, this is a classic
 * "resource allocation" DP problem.
 * The penalty condition can be modeled as a simple transformation.
 *
 *    sum(w_i)         >= W + k * P
 * => sum(w_i) - k * P >= W
 * ...where we define "effective work" E = sum(w_i) - k * P.
 * Clearly, we have again
 *                   E >= W
 *
 * Now, we minimize the cost over E instead of sum(w_i).
 *
 */
auto dp1(const vector<double> &load_f, const vector<double> &capacity_f,
         const CostFunction<double> auto &cost_f, const double tot_work_f,
         const double penalty_f, const int resolution = 1000) -> auto {
    const auto n = static_cast<int>(load_f.size());
    // discretization
    const auto max_capacity = *ranges::max_element(capacity_f);
    const auto e_work = tot_work_f / resolution;
    const auto tot_work = static_cast<int>(ceil(tot_work_f / e_work));
    auto load = vector<int>(n);
    transform(execution::par, load_f.begin(), load_f.end(), load.begin(),
              [e_work](double x) -> int {
                  return static_cast<int>(ceil(x / e_work));
              });
    auto capacity = vector<int>(n);
    transform(execution::par, capacity_f.begin(), capacity_f.end(),
              capacity.begin(), [e_work](double x) -> int {
                  return static_cast<int>(floor(x / e_work));
              });
    const struct {
        decltype(cost_f) &cost_f;
        double e_work;
        auto operator[](int i) const {
            return
                [&, i](int load) -> double { return cost_f[i](load * e_work); };
        }
    } cost{.cost_f = cost_f, .e_work = e_work};
    const auto penalty = static_cast<int>(round(penalty_f / e_work));

    // p = dp[i][w] = minimum cost to allocate w effective work in the first i
    // blocks. p[0] is when the last block is allocated, p[1] is when the
    // last block is not
    constexpr auto inf = numeric_limits<double>::max() / 2;
    auto dp = vector(n + 1, vector(tot_work + 1, array{inf, inf}));
    for (auto &row : dp)
        row[0][1] = 0.; // 0 cost for 0 work
    // for {w_i} reconstruction; for W = w, w_i = res[i][w]
    auto res = vector(n + 1, vector(tot_work + 1, array<pair<int, int>, 2>{}));

    for (const auto i : views::iota(1, n + 1)) {
        const auto cost_func = cost[i - 1];
        // do no work
        for (const auto [w_prev, prev] : views::enumerate(dp[i - 1])) {
            const auto b = prev[0] < prev[1];
            const auto new_cost = b ? prev[0] : prev[1];
            const auto w = w_prev;
            if (new_cost < dp[i][w][1]) {
                dp[i][w][1] = new_cost;
                res[i][w][1] = {0, b};
            }
        }
        // do some work
        for (const auto wi :
             views::iota(1, capacity[i - 1] - load[i - 1] + 1)) {
            for (const auto w_prev : views::iota(0, tot_work + 1)) {
                const auto &prev = dp[i - 1][w_prev];
                const auto add_cost =
                    cost_func(wi + load[i - 1]) - cost_func(load[i - 1]);
                { // extend run
                    const auto new_cost = prev[0] + add_cost;
                    const auto w = min(w_prev + wi, tot_work);
                    if (new_cost < dp[i][w][0]) {
                        dp[i][w][0] = new_cost;
                        res[i][w][0] = {wi, 0};
                    }
                }
                { // start new run
                    const auto new_cost = prev[1] + add_cost;
                    const auto w = min(w_prev + wi - penalty, tot_work);
                    if (w >= 0 && new_cost < dp[i][w][0]) {
                        dp[i][w][0] = new_cost;
                        res[i][w][0] = {wi, 1};
                    }
                }
            }
        }
    }

    return pair{std::move(dp), std::move(res)};
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
