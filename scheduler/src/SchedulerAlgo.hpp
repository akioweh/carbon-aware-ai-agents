#ifndef SCHEDULER_SCHEDULER_ALGO_HPP
#define SCHEDULER_SCHEDULER_ALGO_HPP
#pragma once

#include "exceptions/SchedulingException.hpp"
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <execution>
#include <future>
#include <immintrin.h>
#include <limits>
#include <ranges>
#include <utility>
#include <vector>

namespace scheduler {

template <typename Self, typename T>
concept CostFunction = requires(Self &f, int i, T load) {
    { f[i](load) } -> std::convertible_to<double>;
};

using CostVector = std::vector<double>;

// Memo entry: {alloc, prev_state, w_prev}.
// alloc     – work units allocated at this block
// prev_state – the state (0=active-run, 1=idle) at the previous block
// w_prev    – the effective-work level at the previous block
//
// Storing w_prev explicitly is critical because the forward DP clamps
// w = min(w_prev + wi, tot_work), so multiple (w_prev, wi) combos may map
// to the same clamped w.  Without the stored w_prev, reconstruction can't
// recover the true predecessor, causing allocations to not sum correctly.
struct MemoEntry {
    int alloc = 0;
    int prev_state = 0;
    int w_prev = 0;
};

struct MemoEntryVector {
    std::vector<int> alloc, prev_state, w_prev;

    MemoEntryVector(size_t size)
        : alloc(size, 0), prev_state(size, 0), w_prev(size, 0) {}

    struct Reference {
        int &alloc, &prev_state, &w_prev;
        void operator=(const Reference &other) {
            alloc = other.alloc;
            prev_state = other.prev_state;
            w_prev = other.w_prev;
        }
        void operator=(const std::array<int, 3> &vals) {
            alloc = vals[0];
            prev_state = vals[1];
            w_prev = vals[2];
        }
    };
    auto operator[](size_t idx) {
        return Reference{.alloc = alloc[idx],
                         .prev_state = prev_state[idx],
                         .w_prev = w_prev[idx]};
    }

    auto operator[](size_t idx) const -> MemoEntry {
        return MemoEntry{.alloc = alloc[idx],
                         .prev_state = prev_state[idx],
                         .w_prev = w_prev[idx]};
    }
};

using ChoiceVector = std::vector<std::array<MemoEntryVector, 2>>;
using SingleResult = std::pair<CostVector, ChoiceVector>;

struct LocationCost {
    std::vector<double> &carbon_intensity;
    double kwh_per_flo;

    auto operator[](size_t i) const {
        const auto ci = carbon_intensity.at(i);
        return [ci, efficiency = kwh_per_flo](double load) -> double {
            return load * efficiency * ci;
        };
    }
};

// SIMD lane count
// 512 bits = 64 bytes.
constexpr int VEC_SIZE = 512 / 8 / sizeof(double);

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
inline void vectorizeDpTransition(const int w_prev, const int tot_work,
                                  const std::vector<double> &cost_table,
                                  const double prev0, const double prev1,
                                  std::vector<double> &row0, auto &memo_entry,
                                  const int max_wi, const int penalty) {

    const auto sequence = _mm256_setr_epi32(0, 1, 2, 3, 4, 5, 6, 7);
    const auto zeros = _mm256_set1_epi32(0);
    const auto ones = _mm256_set1_epi32(1);
    const auto w_prevV = _mm256_set1_epi32(w_prev);

    const auto prev0V = _mm512_set1_pd(prev0);
    const auto prev1V = _mm512_set1_pd(prev1);

    auto transitionAVX = [&](const int start_wi, const int end_wi,
                             auto &&prevxV, auto &&stateV,
                             const int penalty = 0) -> void {
        for (auto wi = start_wi; wi <= end_wi; wi += VEC_SIZE) {
            const auto targetRowIndex = w_prev + wi - penalty;
            const auto add_cost = _mm512_loadu_pd(&cost_table[wi]);
            const auto new_cost = _mm512_add_pd(prevxV, add_cost);
            const auto row0V = _mm512_loadu_pd(&row0[targetRowIndex]);
            const __mmask8 maskForMemo =
                _mm512_cmp_pd_mask(new_cost, row0V, _CMP_LT_OS);

            if (maskForMemo) {
                _mm512_mask_storeu_pd(&row0[targetRowIndex], maskForMemo,
                                      new_cost);

                auto wiV = _mm256_set1_epi32(wi);
                wiV = _mm256_add_epi32(wiV, sequence);
                _mm256_mask_storeu_epi32(&memo_entry.alloc[targetRowIndex],
                                         maskForMemo, wiV);
                _mm256_mask_storeu_epi32(&memo_entry.prev_state[targetRowIndex],
                                         maskForMemo, stateV);
                _mm256_mask_storeu_epi32(&memo_entry.w_prev[targetRowIndex],
                                         maskForMemo, w_prevV);
            }
        }
    };

    constexpr int start_wi_extend = 1;
    const int end_wi_extend = std::min(max_wi, tot_work - w_prev);
    transitionAVX(start_wi_extend, end_wi_extend, prev0V, zeros);

    // NOTE: actually, is this clamping correct? could we temporarily take on
    // negative effective work?
    const int start_wi_new_run = std::max(1, penalty - w_prev);
    const int end_wi_new_run = std::min(max_wi, tot_work + penalty - w_prev);
    transitionAVX(start_wi_new_run, end_wi_new_run, prev1V, ones, penalty);
}

inline auto get_e_work(const double tot_work_f, const int resolution)
    -> double {
    constexpr double min_e_work = 0.001;
    return std::max(tot_work_f / resolution, min_e_work);
}

inline auto calc_single(const std::vector<double> &load_f,
                        const std::vector<double> &capacity_f,
                        const CostFunction<double> auto &cost_f,
                        const double penalty_f, const double tot_work_f,
                        const int resolution = 10000) -> SingleResult {
    using namespace std;
    const auto n = static_cast<int>(load_f.size());
    // discretization
    const auto e_work = get_e_work(tot_work_f, resolution);
    const auto tot_work = static_cast<int>(ceil(tot_work_f / e_work));
    auto load = vector<int>(n);
    transform(execution::unseq, load_f.begin(), load_f.end(), load.begin(),
              [e_work](double x) -> int {
                  return static_cast<int>(ceil(x / e_work));
              });
    auto capacity = vector<int>(n);
    transform(execution::unseq, capacity_f.begin(), capacity_f.end(),
              capacity.begin(), [e_work](double x) -> int {
                  return static_cast<int>(floor(x / e_work));
              });
    const struct {
        decltype(cost_f) &cost_f_;
        double e_work;
        auto operator[](size_t i) const {
            return [&, i](int load) -> double {
                return cost_f_[i](load * e_work);
            };
        }
    } cost{.cost_f_ = cost_f, .e_work = e_work};
    const auto penalty = static_cast<int>(round(penalty_f / e_work));

    // p = dp[i][w] = minimum cost to allocate w effective work in the first
    // i blocks. p[0] is when the last block is allocated, p[1] is when the
    // last block is not
    const int sizeOfDpWithPadding = tot_work + 1 + VEC_SIZE;
    constexpr auto inf = numeric_limits<double>::max() / 2;
    auto row = array{vector(sizeOfDpWithPadding, inf),
                     vector(sizeOfDpWithPadding, inf)};

    auto prev_row = row;
    row[1][0] = 0.; // 0 cost for 0 work
    // for {w_i} reconstruction; for W = w, w_i = memo[i][w]
    auto memo = vector(n + 1, array{MemoEntryVector(sizeOfDpWithPadding),
                                    MemoEntryVector(sizeOfDpWithPadding)});

    int max_wi_precomputed{0};
    for (auto i : capacity)
        max_wi_precomputed = max(max_wi_precomputed, i);

    auto cost_table = vector(max_wi_precomputed + 1 + VEC_SIZE, inf);

    for (const auto i : views::iota(1, n + 1)) {
        swap(row, prev_row);

        ranges::fill(row[0], inf);
        ranges::fill(row[1], inf);

        const auto cost_func = cost[i - 1];
        const auto max_wi = max(0, capacity[i - 1] - load[i - 1]);
        const auto base_cost = cost_func(load[i - 1]);

        for (int wi = 0; wi <= max_wi; wi++)
            cost_table[wi] = cost_func(wi + load[i - 1]) - base_cost;

        for (const auto w_prev : views::iota(0, tot_work + 1)) {
            const auto &[prev0, prev1] =
                array{prev_row[0][w_prev], prev_row[1][w_prev]};
            // do no work (propagate to same w)
            {
                const auto from_active = prev0 < prev1;
                const auto new_cost = from_active ? prev0 : prev1;
                if (new_cost < row[1][w_prev]) {
                    row[1][w_prev] = new_cost;
                    memo[i][1][w_prev] =
                        std::array{0, from_active ? 0 : 1, w_prev};
                }
            }
            // do some work
            vectorizeDpTransition(w_prev, tot_work, cost_table, prev0, prev1,
                                  row[0], memo[i][0], max_wi, penalty);
        }
    }

    // we made it cache friendly, now back to previous structure
    auto help_row = vector(tot_work + 1, array{inf, inf});
    for (int i = 0; i <= tot_work; i++)
        help_row[i] = {row[0][i], row[1][i]};

    auto res = vector<double>{};
    res.reserve(tot_work + 1);
    for (const auto &[w, costs] : views::enumerate(help_row)) {
        // other than condensing the dp cost results,
        // we also want to set the last memo entry based on our choices here
        // (costs[0] vs costs[1]) for easier reconstruction later
        if (costs[0] < costs[1]) {
            res.push_back(costs[0]);
            memo[n][1][w] = memo[n][0][w];
        } else {
            res.push_back(costs[1]);
            memo[n][0][w] = memo[n][1][w];
        }
    }
    return {std::move(res), std::move(memo)};
}

/*
 * Runs calc_single for each location in parallel, then merges results using
 * a multiple-choice knapsack DP.
 *
 * Currently uses std::async(std::launch::async, ...) for expressive
 * threading control.
 *
 * Throws SchedulingException if the problem is infeasible.
 */
template <typename CostFunc>
    requires CostFunction<CostFunc, double>
auto calc_multiple(const std::vector<std::vector<double>> &loads_f,
                   const std::vector<std::vector<double>> &capacities_f,
                   const std::vector<CostFunc> &costs_f,
                   const std::vector<double> &penalties_f,
                   const double tot_work_f, const int resolution = 10000)
    -> std::pair<double, std::vector<std::vector<double>>> {
    using namespace std;
    const auto m = loads_f.size();
    if (m == 0)
        throw exceptions::SchedulingException(
            "No locations provided for scheduling");
    const auto n = loads_f.front().size();
    // input validation
    assert(tot_work_f >= 0.);
    assert(resolution > 0);
    assert(capacities_f.size() == m);
    assert(costs_f.size() == m);
    assert(penalties_f.size() == m);
    assert(ranges::all_of(
        loads_f, [n](const auto &load_f) { return load_f.size() == n; }));
    assert(ranges::all_of(capacities_f, [n](const auto &capacity_f) {
        return capacity_f.size() == n;
    }));

    // thread-parallism using std::async(std::launch::async, ...)
    auto futures = vector<future<SingleResult>>{};
    futures.reserve(m);
    for (const auto i : views::iota(0UZ, m))
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
    for (auto i : views::iota(0UZ, m))
        tie(locations_cost_vector[i], locations_memo[i]) = futures[i].get();

    const auto e_work = get_e_work(tot_work_f, resolution);
    const auto tot_work = static_cast<int>(ceil(tot_work_f / e_work));

    // result validation
    assert(ranges::all_of(locations_memo, [n](const auto &vec) {
        return vec.size() == n + 1UZ;
    }));
    assert(ranges::all_of(locations_cost_vector, [tot_work](const auto &vec) {
        return vec.size() == tot_work + 1UZ;
    }));

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
    for (const auto i : views::iota(1UZ, m)) {
        const auto &costs = locations_cost_vector[i];
        auto next_dp = vector(tot_work + 1, inf);
        auto &memo_i = memo[i];
        // each w is independent: reads dp and costs,
        // writes only to next_dp[w] and memo_i[w]
        const auto w_range = views::iota(0, tot_work + 1);
        for_each(execution::par_unseq, w_range.begin(), w_range.end(),
                 [&dp = as_const(dp), &costs, &next_dp, &memo_i,
                  inf](const auto w) -> auto {
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
        throw exceptions::SchedulingException(
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
    for (const auto i : views::iota(0UZ, m)) {
        const auto &loc_memo = locations_memo[i];
        auto &loc_res = res[i];
        loc_res.resize(n);

        int cur_w = location_w[i];
        // index 0 always holds the best path info at the end (see bottom of
        // calc_single)
        int cur_state = 0;
        for (auto j = n; j--;) {
            const auto &entry = loc_memo[j + 1][cur_state][cur_w];
            loc_res[j] = static_cast<double>(entry.alloc) * e_work;

            cur_w = entry.w_prev;
            cur_state = entry.prev_state;
        }
        assert(cur_w == 0);
    }

    return {final_cost, res};
}

} // namespace scheduler

#endif // SCHEDULER_SCHEDULER_ALGO_HPP
