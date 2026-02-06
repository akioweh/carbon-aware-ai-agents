#include "Scheduler.hpp"
#include "Calendar.hpp"
#include "StatsAPIClient.hpp"
#include "exceptions/SchedulingException.hpp"
#include "structs/JobRequest.hpp"
#include "utils/Coro.hpp"
#include <algorithm>
#include <cmath>
#include <execution>
#include <future>
#include <limits>
#include <vector>

using namespace std;
using namespace drogon;

template <typename Self, typename T>
concept CostFunction = requires(Self &f, int i, T load) {
    { f[i](load) } -> std::convertible_to<double>;
};

using CostVector = vector<double>;
using ChoiceVector = vector<vector<array<pair<int, int>, 2>>>;
using SingleResult = pair<CostVector, ChoiceVector>;

struct LocationCost {
    vector<double> &capacities;
    vector<double> &greenness_scores;

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
    auto prev_row = vector(tot_work + 1, array{inf, inf});
    row[0][1] = 0.; // 0 cost for 0 work
    // for {w_i} reconstruction; for W = w, w_i = memo[i][w]
    auto memo = vector(n + 1, vector(tot_work + 1, array<pair<int, int>, 2>{}));

    for (const auto i : views::iota(1, n + 1)) {
        swap(row, prev_row);
        ranges::fill(row, array{inf, inf});
        const auto cost_func = cost[i - 1];
        const auto max_wi = capacity[i - 1] - load[i - 1];
        const auto base_cost = cost_func(load[i - 1]);
        for (const auto w_prev : views::iota(0, tot_work + 1)) {
            const auto &prev = prev_row[w_prev];
            // do no work (propagate to same w)
            {
                const auto b = prev[0] < prev[1];
                const auto new_cost = b ? prev[0] : prev[1];
                if (new_cost < row[w_prev][1]) {
                    row[w_prev][1] = new_cost;
                    memo[i][w_prev][1] = {0, b};
                }
            }
            // do some work
            for (const auto wi : views::iota(1, max_wi + 1)) {
                const auto add_cost = cost_func(wi + load[i - 1]) - base_cost;
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
        auto &memo_i = memo[i];
        // each w is independent: reads dp (immutable this pass) and costs,
        // writes only to next_dp[w] and memo_i[w]
        auto w_range = views::iota(0, tot_work + 1);
        for_each(execution::par, w_range.begin(), w_range.end(),
                 [&dp, &costs, &next_dp, &memo_i, inf](const auto w) -> auto {
                     for (const auto k : views::iota(0, w + 1)) {
                         const auto prev_cost = dp[w - k];
                         if (prev_cost >= inf)
                             continue;

                         const auto new_cost = prev_cost + costs[k];
                         if (new_cost < next_dp[w]) {
                             next_dp[w] = new_cost;
                             memo_i[w] = k;
                         }
                     }
                 });
        dp = std::move(next_dp);
    }

    const auto final_cost = dp[tot_work];

    if (final_cost >= inf)
        throw SchedulingException(
            "Infeasible: insufficient capacity across all locations to "
            "satisfy the requested workload within the given time window");

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
        assert(cur_w == 0);
    }

    return {final_cost, res};
}

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
    const auto [locations, existing_schedule] =
        co_await scheduler::coro::when_all(
            stats_api.getAllDatacenters(),
            calendarService::get(time_window_start, time_window_end));
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
