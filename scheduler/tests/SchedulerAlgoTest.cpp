#define BOOST_TEST_MODULE SchedulerAlgoTest
#include <SchedulerAlgo.hpp>
#include <boost/test/included/unit_test.hpp>
#include <cmath>
#include <numeric>

// =============================================================================
// Helpers
// =============================================================================

/// A simple cost function where cost[i](load) = load / capacity / greenness.
/// Mirrors LocationCost but owns its data so tests don't need dangling-ref
/// gymnastics.
struct TestCost {
    std::vector<double> capacities;
    std::vector<double> greenness;

    auto operator[](int i) const {
        const auto g = greenness.at(i);
        const auto c = capacities.at(i);
        return [g, c](double load) -> double {
            return load / c / std::max(g, 0.01);
        };
    }
};

static_assert(CostFunction<TestCost, double>);

/// Sum a 1-D allocation vector (continuous values).
static auto sum_alloc(const std::vector<double> &v) -> double {
    return std::accumulate(v.begin(), v.end(), 0.0);
}

/// Total work across all locations and time slots.
static auto total_work(const std::vector<std::vector<double>> &allocs)
    -> double {
    auto s = 0.0;
    for (const auto &loc : allocs)
        s += sum_alloc(loc);
    return s;
}

// Use a moderate resolution for unit tests — lower for speed, but high enough
// that discretization doesn't cause reconstruction failures.
constexpr int TEST_RES = 50;

// =============================================================================
// Test Suite: calc_single basics
// =============================================================================

BOOST_AUTO_TEST_SUITE(CalcSingle)

BOOST_AUTO_TEST_CASE(zero_work_produces_zero_cost) {
    // 4 blocks, no existing load, uniform capacity & greenness
    const auto n = 4;
    auto load = std::vector<double>(n, 0.0);
    auto cap = std::vector<double>(n, 10.0);
    auto green = std::vector<double>(n, 50.0);
    auto cost = TestCost{cap, green};

    // ask for 0 work — tot_work_f must be >0 for the discretization (e_work),
    // but the cost vector should have cost[0] == 0
    const auto work = 1.0; // we'll check the first entry
    auto [costs, memo] = calc_single(load, cap, cost, 0.0, work, TEST_RES);

    BOOST_CHECK_CLOSE(costs.front(), 0.0, 1e-9);
}

BOOST_AUTO_TEST_CASE(allocates_at_least_requested_work) {
    const auto n = 6;
    auto load = std::vector<double>(n, 2.0);
    auto cap = std::vector<double>(n, 10.0);
    auto green = std::vector<double>(n, 50.0);
    auto cost = TestCost{cap, green};

    const auto requested = 20.0;
    auto [costs, memo] = calc_single(load, cap, cost, 0.0, requested, TEST_RES);

    // reconstruct from memo for the full work amount
    const auto tot_work = static_cast<int>(std::ceil(requested / (requested / TEST_RES)));
    // The cost vector should have tot_work+1 entries
    BOOST_CHECK_EQUAL(costs.size(), static_cast<std::size_t>(tot_work + 1));
    // The cost at the max work level should be finite
    BOOST_CHECK_LT(costs.back(), std::numeric_limits<double>::max() / 4);
}

BOOST_AUTO_TEST_CASE(cost_is_monotonically_non_decreasing) {
    const auto n = 5;
    auto load = std::vector<double>(n, 1.0);
    auto cap = std::vector<double>(n, 10.0);
    auto green = std::vector<double>(n, 40.0);
    auto cost = TestCost{cap, green};

    auto [costs, memo] = calc_single(load, cap, cost, 0.0, 30.0, TEST_RES);

    for (std::size_t i = 1; i < costs.size(); ++i) {
        BOOST_CHECK_GE(costs[i], costs[i - 1] - 1e-9);
    }
}

BOOST_AUTO_TEST_CASE(infeasible_returns_inf_cost) {
    // 2 blocks, existing load fills most capacity — not enough room for 100
    // units of work
    const auto n = 2;
    auto load = std::vector<double>(n, 9.0);
    auto cap = std::vector<double>(n, 10.0);  // only 1 unit free per block
    auto green = std::vector<double>(n, 50.0);
    auto cost = TestCost{cap, green};

    const auto requested = 100.0;
    auto [costs, memo] =
        calc_single(load, cap, cost, 0.0, requested, TEST_RES);

    // The cost at the maximum work level should be infinite (infeasible)
    const auto inf = std::numeric_limits<double>::max() / 2;
    BOOST_CHECK_GE(costs.back(), inf);
}

BOOST_AUTO_TEST_CASE(prefers_greener_blocks) {
    // 2 blocks: block 0 has low greenness, block 1 has high greenness
    auto load = std::vector<double>{0.0, 0.0};
    auto cap = std::vector<double>{10.0, 10.0};
    auto green = std::vector<double>{1.0, 100.0};
    auto cost = TestCost{cap, green};

    const auto requested = 5.0;
    auto [costs, memo] =
        calc_single(load, cap, cost, 0.0, requested, TEST_RES);

    // Reconstruct the allocation for the full work amount
    const auto e_work = requested / TEST_RES;
    const auto tot_work = static_cast<int>(std::ceil(requested / e_work));
    const auto n = 2;

    int cur_w = tot_work;
    int cur_state = 0;
    auto alloc = std::vector<double>(n, 0.0);
    for (auto j = n; j--;) {
        const auto &entry = memo[j + 1][cur_w][cur_state];
        alloc[j] = static_cast<double>(entry.alloc) * e_work;
        cur_w = entry.w_prev;
        cur_state = entry.prev_state;
    }

    // Block 1 (greenness=100) should get more work than block 0 (greenness=1)
    BOOST_TEST_MESSAGE("Alloc to low-green block: " << alloc[0]
                                                    << ", high-green block: "
                                                    << alloc[1]);
    BOOST_CHECK_GT(alloc[1], alloc[0]);
}

BOOST_AUTO_TEST_SUITE_END()

// =============================================================================
// Test Suite: calc_single penalty behavior
// =============================================================================

BOOST_AUTO_TEST_SUITE(CalcSinglePenalty)

BOOST_AUTO_TEST_CASE(penalty_increases_cost_for_fragmented_allocation) {
    // 4 blocks with alternating greenness: forces fragmentation
    auto load = std::vector<double>{0, 0, 0, 0};
    auto cap = std::vector<double>{10, 10, 10, 10};
    // block 0,2 are green, 1,3 are not — optimizer might skip 1,3
    auto green = std::vector<double>{80, 1, 80, 1};
    auto cost_obj = TestCost{cap, green};

    const auto work = 10.0;

    auto [costs_no_penalty, _1] =
        calc_single(load, cap, cost_obj, 0.0, work, TEST_RES);
    auto [costs_with_penalty, _2] =
        calc_single(load, cap, cost_obj, 2.0, work, TEST_RES);

    // With penalty, the cost at maximum work should be >= the no-penalty cost
    BOOST_CHECK_GE(costs_with_penalty.back(),
                   costs_no_penalty.back() - 1e-9);
}

BOOST_AUTO_TEST_SUITE_END()

// =============================================================================
// Test Suite: calc_multiple basics
// =============================================================================

BOOST_AUTO_TEST_SUITE(CalcMultiple)

BOOST_AUTO_TEST_CASE(single_location_matches_single) {
    // With 1 location, calc_multiple should produce the same cost as
    // calc_single
    const auto n = 4;
    auto loads = std::vector<std::vector<double>>{std::vector<double>(n, 1.0)};
    auto caps =
        std::vector<std::vector<double>>{std::vector<double>(n, 10.0)};
    auto greens_vec =
        std::vector<std::vector<double>>{std::vector<double>(n, 50.0)};
    auto cost_obj = TestCost{caps[0], greens_vec[0]};
    auto costs_vec = std::vector{cost_obj};
    auto penalties = std::vector{0.0};

    const auto work = 15.0;
    auto [cost_multi, allocs] =
        calc_multiple(loads, caps, costs_vec, penalties, work, TEST_RES);

    BOOST_CHECK_EQUAL(allocs.size(), 1ULL);
    BOOST_CHECK_EQUAL(allocs[0].size(), static_cast<std::size_t>(n));

    // total allocated work should be >= requested
    const auto alloc_sum = sum_alloc(allocs[0]);
    BOOST_CHECK_GE(alloc_sum, work - 1e-3);

    // cost should be finite and positive
    BOOST_CHECK_GT(cost_multi, 0.0);
    BOOST_CHECK_LT(cost_multi, std::numeric_limits<double>::max() / 4);
}

BOOST_AUTO_TEST_CASE(total_allocation_meets_demand) {
    const auto n = 5;
    auto loads = std::vector{std::vector<double>(n, 0.0),
                             std::vector<double>(n, 0.0)};
    auto caps = std::vector{std::vector<double>(n, 10.0),
                            std::vector<double>(n, 10.0)};
    auto greens1 = std::vector<double>(n, 60.0);
    auto greens2 = std::vector<double>(n, 40.0);
    auto greens = std::vector{greens1, greens2};
    auto cost1 = TestCost{caps[0], greens[0]};
    auto cost2 = TestCost{caps[1], greens[1]};
    auto costs = std::vector{cost1, cost2};
    auto penalties = std::vector{0.0, 0.0};

    const auto work = 30.0;
    auto [cost, allocs] =
        calc_multiple(loads, caps, costs, penalties, work, TEST_RES);

    BOOST_CHECK_GE(total_work(allocs), work - 1e-3);
}

BOOST_AUTO_TEST_CASE(respects_capacity_constraints) {
    const auto n = 4;
    auto loads = std::vector{std::vector<double>(n, 5.0),
                             std::vector<double>(n, 3.0)};
    auto caps = std::vector{std::vector<double>(n, 8.0),
                            std::vector<double>(n, 10.0)};
    auto greens1 = std::vector<double>(n, 50.0);
    auto greens2 = std::vector<double>(n, 50.0);
    auto greens = std::vector{greens1, greens2};
    auto cost1 = TestCost{caps[0], greens[0]};
    auto cost2 = TestCost{caps[1], greens[1]};
    auto costs = std::vector{cost1, cost2};
    auto penalties = std::vector{0.0, 0.0};

    const auto work = 20.0;
    auto [cost, allocs] =
        calc_multiple(loads, caps, costs, penalties, work, TEST_RES);

    // For each location and time slot, load + allocation <= capacity
    for (std::size_t loc = 0; loc < allocs.size(); ++loc) {
        for (std::size_t t = 0; t < allocs[loc].size(); ++t) {
            const auto total = loads[loc][t] + allocs[loc][t];
            BOOST_CHECK_LE(total, caps[loc][t] + 1e-3);
        }
    }
}

BOOST_AUTO_TEST_CASE(allocations_are_non_negative) {
    const auto n = 5;
    auto loads = std::vector{std::vector<double>(n, 2.0),
                             std::vector<double>(n, 1.0),
                             std::vector<double>(n, 3.0)};
    auto caps = std::vector{std::vector<double>(n, 10.0),
                            std::vector<double>(n, 10.0),
                            std::vector<double>(n, 10.0)};
    auto greens1 = std::vector<double>(n, 30.0);
    auto greens2 = std::vector<double>(n, 60.0);
    auto greens3 = std::vector<double>(n, 90.0);
    auto greens = std::vector{greens1, greens2, greens3};
    auto cost1 = TestCost{caps[0], greens[0]};
    auto cost2 = TestCost{caps[1], greens[1]};
    auto cost3 = TestCost{caps[2], greens[2]};
    auto costs = std::vector{cost1, cost2, cost3};
    auto penalties = std::vector{0.0, 0.0, 0.0};

    const auto work = 25.0;
    auto [cost, allocs] =
        calc_multiple(loads, caps, costs, penalties, work, TEST_RES);

    for (const auto &loc_alloc : allocs)
        for (const auto a : loc_alloc)
            BOOST_CHECK_GE(a, -1e-9);
}

BOOST_AUTO_TEST_CASE(prefers_greener_location) {
    // Two locations with same capacity and load, but different greenness
    const auto n = 4;
    auto loads = std::vector{std::vector<double>(n, 0.0),
                             std::vector<double>(n, 0.0)};
    auto caps = std::vector{std::vector<double>(n, 20.0),
                            std::vector<double>(n, 20.0)};
    auto greens1 = std::vector<double>(n, 5.0);  // low greenness
    auto greens2 = std::vector<double>(n, 95.0); // high greenness
    auto greens = std::vector{greens1, greens2};
    auto cost1 = TestCost{caps[0], greens[0]};
    auto cost2 = TestCost{caps[1], greens[1]};
    auto costs = std::vector{cost1, cost2};
    auto penalties = std::vector{0.0, 0.0};

    const auto work = 20.0;
    auto [cost, allocs] =
        calc_multiple(loads, caps, costs, penalties, work, TEST_RES);

    const auto loc0_total = sum_alloc(allocs[0]);
    const auto loc1_total = sum_alloc(allocs[1]);
    BOOST_TEST_MESSAGE("Low-green location: " << loc0_total
                                              << ", high-green location: "
                                              << loc1_total);
    // High greenness location should receive more work
    BOOST_CHECK_GT(loc1_total, loc0_total);
}

BOOST_AUTO_TEST_CASE(throws_on_infeasible_workload) {
    // Tiny capacity, huge requested work
    const auto n = 2;
    auto loads =
        std::vector<std::vector<double>>{std::vector<double>(n, 9.0)};
    auto caps =
        std::vector<std::vector<double>>{std::vector<double>(n, 10.0)};
    auto greens =
        std::vector<std::vector<double>>{std::vector<double>(n, 50.0)};
    auto cost = TestCost{caps[0], greens[0]};
    auto costs = std::vector{cost};
    auto penalties = std::vector{0.0};

    // Only 2 units free total, asking for 500
    BOOST_CHECK_THROW(
        calc_multiple(loads, caps, costs, penalties, 500.0, TEST_RES),
        SchedulingException);
}

BOOST_AUTO_TEST_CASE(cost_decreases_with_more_locations) {
    // Adding a second location should not increase cost
    const auto n = 4;
    auto loads1 =
        std::vector<std::vector<double>>{std::vector<double>(n, 0.0)};
    auto caps1 =
        std::vector<std::vector<double>>{std::vector<double>(n, 10.0)};
    auto greens1_vec =
        std::vector<std::vector<double>>{std::vector<double>(n, 50.0)};
    auto cost1 = TestCost{caps1[0], greens1_vec[0]};
    auto costs1 = std::vector{cost1};
    auto penalties1 = std::vector{0.0};

    auto loads2 = std::vector{std::vector<double>(n, 0.0),
                              std::vector<double>(n, 0.0)};
    auto caps2 = std::vector{std::vector<double>(n, 10.0),
                             std::vector<double>(n, 10.0)};
    auto greens2_vec = std::vector{std::vector<double>(n, 50.0),
                                   std::vector<double>(n, 50.0)};
    auto cost2a = TestCost{caps2[0], greens2_vec[0]};
    auto cost2b = TestCost{caps2[1], greens2_vec[1]};
    auto costs2 = std::vector{cost2a, cost2b};
    auto penalties2 = std::vector{0.0, 0.0};

    const auto work = 20.0;
    auto [cost_1loc, _1] =
        calc_multiple(loads1, caps1, costs1, penalties1, work, TEST_RES);
    auto [cost_2loc, _2] =
        calc_multiple(loads2, caps2, costs2, penalties2, work, TEST_RES);

    BOOST_CHECK_LE(cost_2loc, cost_1loc + 1e-9);
}

BOOST_AUTO_TEST_SUITE_END()

// =============================================================================
// Test Suite: calc_multiple with LocationCost (the real cost function)
// =============================================================================

BOOST_AUTO_TEST_SUITE(CalcMultipleLocationCost)

BOOST_AUTO_TEST_CASE(works_with_LocationCost) {
    // Verify the algorithm works with the real LocationCost struct, which holds
    // references into external vectors — the same pattern used in Scheduler.cpp
    const auto n = 4;
    auto caps = std::vector{std::vector<double>(n, 10.0),
                            std::vector<double>(n, 10.0)};
    auto greens = std::vector{std::vector<double>(n, 50.0),
                              std::vector<double>(n, 80.0)};
    // LocationCost holds references; vectors must not reallocate after this
    auto costs = std::vector<LocationCost>{};
    costs.reserve(2);
    costs.emplace_back(caps[0], greens[0]);
    costs.emplace_back(caps[1], greens[1]);

    auto loads = std::vector{std::vector<double>(n, 0.0),
                             std::vector<double>(n, 0.0)};
    auto penalties = std::vector{0.0, 0.0};

    const auto work = 15.0;
    auto [cost, allocs] =
        calc_multiple(loads, caps, costs, penalties, work, TEST_RES);

    BOOST_CHECK_GE(total_work(allocs), work - 1e-3);
    BOOST_CHECK_GT(cost, 0.0);
    BOOST_CHECK_LT(cost, std::numeric_limits<double>::max() / 4);

    // Greener location should get more work
    BOOST_CHECK_GT(sum_alloc(allocs[1]), sum_alloc(allocs[0]));
}

BOOST_AUTO_TEST_SUITE_END()

// =============================================================================
// Test Suite: edge cases
// =============================================================================

BOOST_AUTO_TEST_SUITE(EdgeCases)

BOOST_AUTO_TEST_CASE(single_block_single_location) {
    // Simplest possible case: 1 location, 1 time slot
    auto loads =
        std::vector<std::vector<double>>{{0.0}};
    auto caps =
        std::vector<std::vector<double>>{{10.0}};
    auto greens =
        std::vector<std::vector<double>>{{50.0}};
    auto cost = TestCost{caps[0], greens[0]};
    auto costs = std::vector{cost};
    auto penalties = std::vector{0.0};

    const auto work = 5.0;
    auto [total_cost, allocs] =
        calc_multiple(loads, caps, costs, penalties, work, TEST_RES);

    BOOST_CHECK_EQUAL(allocs.size(), 1ULL);
    BOOST_CHECK_EQUAL(allocs[0].size(), 1ULL);
    BOOST_CHECK_GE(allocs[0][0], work - 1e-3);
}

BOOST_AUTO_TEST_CASE(fully_loaded_blocks_get_zero_allocation) {
    // All blocks at capacity — should allocate 0 to them and find work
    // elsewhere
    const auto n = 3;
    auto loads = std::vector{
        std::vector<double>(n, 10.0), // loc 0: fully loaded
        std::vector<double>(n, 0.0),  // loc 1: empty
    };
    auto caps = std::vector{std::vector<double>(n, 10.0),
                            std::vector<double>(n, 10.0)};
    auto greens = std::vector{std::vector<double>(n, 50.0),
                              std::vector<double>(n, 50.0)};
    auto cost1 = TestCost{caps[0], greens[0]};
    auto cost2 = TestCost{caps[1], greens[1]};
    auto costs = std::vector{cost1, cost2};
    auto penalties = std::vector{0.0, 0.0};

    const auto work = 10.0;
    auto [cost, allocs] =
        calc_multiple(loads, caps, costs, penalties, work, TEST_RES);

    // Location 0 should get ~0 allocation (it's full)
    BOOST_CHECK_SMALL(sum_alloc(allocs[0]), 1e-3);
    // Location 1 should absorb all the work
    BOOST_CHECK_GE(sum_alloc(allocs[1]), work - 1e-3);
}

BOOST_AUTO_TEST_CASE(varying_capacity_across_time_slots) {
    // Time slots with different capacities — work should be allocated to
    // slots with more headroom
    const auto n = 4;
    auto loads =
        std::vector<std::vector<double>>{{5, 5, 5, 5}};
    // Slot 0,1 have lots of headroom; slot 2,3 are nearly full
    auto caps =
        std::vector<std::vector<double>>{{20, 20, 6, 6}};
    auto greens =
        std::vector<std::vector<double>>{std::vector<double>(n, 50.0)};
    auto cost = TestCost{caps[0], greens[0]};
    auto costs = std::vector{cost};
    auto penalties = std::vector{0.0};

    const auto work = 10.0;
    auto [total_cost, allocs] =
        calc_multiple(loads, caps, costs, penalties, work, TEST_RES);

    // Slots 0,1 (more headroom) should receive more allocation than 2,3
    const auto headroom_alloc = allocs[0][0] + allocs[0][1];
    const auto tight_alloc = allocs[0][2] + allocs[0][3];
    BOOST_CHECK_GT(headroom_alloc, tight_alloc);
}

BOOST_AUTO_TEST_SUITE_END()
