#include "Scheduler.hpp"
#include "Calendar.hpp"
#include "StatsAPIClient.hpp"
#include "structs/JobRequest.hpp"
#include "structs/ScheduleBlock.hpp"
#include <algorithm>
#include <cmath>
#include <drogon/HttpTypes.h>
#include <execution>
#include <future>
#include <limits>
#include <map>
#include <set>
#include <vector>

using namespace std;
using namespace drogon;

struct LoadBlock {
    std::chrono::system_clock::time_point timestamp;
    double load{};
};

auto operator<=>(const LoadBlock &lhs, const LoadBlock &rhs) -> auto {
    return lhs.timestamp <=> rhs.timestamp;
}

template <typename Self, typename T>
concept CostFunction = requires(Self &f, int i, T load) {
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

using CostVector = vector<double>;
using ChoiceVector = vector<vector<array<pair<int, int>, 2>>>;
using SingleResult = pair<CostVector, ChoiceVector>;

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
auto calc_single(const vector<double> &load_f, const vector<double> &capacity_f,
                 const CostFunction<double> auto &cost_f,
                 const double penalty_f, const double tot_work_f,
                 const int resolution = 1000) -> SingleResult {
    const auto n = static_cast<int>(load_f.size());
    // discretization
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
    auto row = vector(tot_work + 1, array{inf, inf});
    row[0][1] = 0.; // 0 cost for 0 work
    // for {w_i} reconstruction; for W = w, w_i = memo[i][w]
    auto memo = vector(n + 1, vector(tot_work + 1, array<pair<int, int>, 2>{}));

    for (const auto i : views::iota(1, n + 1)) {
        const auto prev_row = row;
        row.assign(tot_work + 1, array{inf, inf});
        const auto cost_func = cost[i - 1];
        // do no work
        for (const auto [w_prev, prev] : views::enumerate(prev_row)) {
            const auto b = prev[0] < prev[1];
            const auto new_cost = b ? prev[0] : prev[1];
            const auto w = w_prev;
            if (new_cost < row[w][1]) {
                row[w][1] = new_cost;
                memo[i][w][1] = {0, b};
            }
        }
        // do some work
        for (const auto wi :
             views::iota(1, capacity[i - 1] - load[i - 1] + 1)) {
            for (const auto w_prev : views::iota(0, tot_work + 1)) {
                const auto &prev = prev_row[w_prev];
                const auto add_cost =
                    cost_func(wi + load[i - 1]) - cost_func(load[i - 1]);
                { // extend run
                    const auto new_cost = prev[0] + add_cost;
                    const auto w = min(w_prev + wi, tot_work);
                    if (new_cost < row[w][0]) {
                        row[w][0] = new_cost;
                        memo[i][w][0] = {wi, 0};
                    }
                }
                { // start new run
                    const auto new_cost = prev[1] + add_cost;
                    const auto w = min(w_prev + wi - penalty, tot_work);
                    if (w >= 0 && new_cost < row[w][0]) {
                        row[w][0] = new_cost;
                        memo[i][w][0] = {wi, 1};
                    }
                }
            }
        }
    }

    auto res = vector<double>{};
    res.reserve(tot_work + 1);
    for (const auto &[w, costs] : views::enumerate(row)) {
        // other than condensing the dp cost results,
        // we also want to set the last memo entry based on our choices here
        // (costs[0] vs costs[1]) for easier reconstruction later
        if (costs[0] < costs[1]) {
            res.push_back(costs[0]);
            memo[n][w][1] = memo[n][w][0];
        } else {
            res.push_back(costs[1]);
            memo[n][w][0] = memo[n][w][1];
        }
    }
    return {std::move(res), std::move(memo)};
}

/*
 * Runs calc_single for each location in parallel, then merges results using a
 * multiple-choice knapsack DP.
 *
 * Currently uses std::async(std::launch::async, ...) for expressive
 * threading control.
 */
template <typename CostFunc>
    requires CostFunction<CostFunc, double>
auto calc_multiple(const vector<vector<double>> &loads_f,
                   const vector<vector<double>> &capacities_f,
                   const vector<CostFunc> &costs_f,
                   const vector<double> &penalties_f, const double tot_work_f,
                   const int resolution = 1000)
    -> pair<double, vector<vector<double>>> {
    const auto m = loads_f.size();
    const auto n = m ? loads_f.front().size() : 0ULL;
    // input validation
    assert(tot_work_f >= 0.);
    assert(resolution > 0);
    assert(capacities_f.size() == m);
    assert(costs_f.size() == m);
    assert(penalties_f.size() == m);
    for (const auto i : views::iota(0ULL, m)) {
        assert(loads_f[i].size() == n);
        assert(capacities_f[i].size() == n);
    }

    // thread-parallism using std::async(std::launch::async, ...)
    auto futures = vector<future<SingleResult>>{};
    futures.reserve(m);
    for (const auto i : views::iota(0ULL, m))
        futures.push_back(async(
            launch::async,
            // wrapped in lambda due to template
            // instantiation issues with CostFunc
            [i, &loads_f, &capacities_f, &costs_f, &penalties_f, tot_work_f,
             resolution]() -> auto {
                return calc_single(loads_f[i], capacities_f[i], costs_f[i],
                                   penalties_f[i], tot_work_f, resolution);
            }));

    auto locations_cost_vector = vector<SingleResult::first_type>(m);
    auto locations_memo = vector<SingleResult::second_type>(m);
    for (auto i : views::iota(0ULL, m))
        tie(locations_cost_vector[i], locations_memo[i]) = futures[i].get();

    const auto e_work = tot_work_f / resolution;
    const auto tot_work = static_cast<int>(ceil(tot_work_f / e_work));

    // result validation
    for (const auto i : views::iota(0ULL, m)) {
        assert(locations_memo[i].size() == n + 1ULL);
        assert(locations_cost_vector[i].size() == tot_work + 1ULL);
    }

    // multiple choice knapsack
    constexpr auto inf = numeric_limits<double>::max() / 2;
    // min cost for [work amount]
    auto dp = vector<double>(tot_work + 1, inf);
    dp[0] = 0.;
    // memo[i][w] = work allocated to location i for total work w
    auto memo = vector<vector<int>>(m, vector<int>(tot_work + 1, 0));

    if (m > 0) {
        const auto &costs = locations_cost_vector[0];
        for (const auto w : views::iota(0, tot_work + 1)) {
            dp[w] = costs[w];
            memo[0][w] = w;
        }
    }
    for (const auto i : views::iota(1ULL, m)) {
        auto next_dp = vector(tot_work + 1, inf);
        const auto &costs = locations_cost_vector[i];
        for (const auto w : views::iota(0, tot_work + 1)) {
            for (const auto k : views::iota(0, w + 1)) {
                const auto prev_cost = dp[w - k];
                if (prev_cost >= inf)
                    continue;

                const auto new_cost = prev_cost + costs[k];
                if (new_cost < next_dp[w]) {
                    next_dp[w] = new_cost;
                    memo[i][w] = k;
                }
            }
        }
        dp = std::move(next_dp);
    }

    const auto final_cost = dp[tot_work];

    // reconstruction
    // res[i][j] = work allocated to location i in block j
    auto res = vector<vector<double>>(m);
    auto remaining_work = tot_work;

    // reconstruct sum(res[i]) for each location i
    auto location_w = vector<int>(m);
    for (auto i = m; i--;) {
        const auto alloc = memo[i][remaining_work];
        location_w[i] = alloc;
        remaining_work -= alloc;
    }

    // reconstruct the {w_j} work allocation vector for each location
    for (const auto i : views::iota(0ULL, m)) {
        const auto &loc_memo = locations_memo[i];
        auto &loc_res = res[i];
        loc_res.resize(n);

        int cur_w = location_w[i];
        // index 0 always holds the best path info at the end (see bottom of
        // calc_single)
        int cur_state = 0;
        for (auto j = n; j--;) {
            const auto &choice = loc_memo[j + 1][cur_w][cur_state];
            const auto [alloc, prev_state] = choice;
            loc_res[j] = static_cast<double>(alloc) * e_work;

            cur_w -= alloc;
            cur_state = prev_state;
        }
    }

    return {final_cost, res};
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
