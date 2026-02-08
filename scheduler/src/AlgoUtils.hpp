#pragma once
#include <algorithm>
#include <array>
#include <limits>
#include <ranges>
#include <vector>

namespace scheduler {

/**
 * @brief Configuration constants for the TimeWindowScheduler.
 * MAX_WORK_RESOLUTION defines the discretization granularity for the Min-Plus
 * Convolution. It strictly limits the MAXIMUM TOTAL WORK that can be
 * queried/reserved in a single request. Increasing this increases memory usage
 * (ProfileMatrix size) and CPU time (O(W^2)).
 */
constexpr int MAX_WORK_RESOLUTION = 200;

// Use std::array for Structural Type support (required for NTTP in SegmentTree)
using CostArray = std::array<double, MAX_WORK_RESOLUTION + 1>;

/**
 * @brief Performs Min-Plus Convolution between two cost arrays.
 *
 * Computes C[k] = min_{i+j=k} (A[i] + B[j])
 *
 * This operation effectively combines two convex (or non-convex) cost
 * functions. In the context of the scheduler, it combines the cost profiles of
 * two time intervals.
 *
 * Complexity: O(W^2) where W is MAX_WORK_RESOLUTION.
 *
 * @param A The left operand cost array.
 * @param B The right operand cost array.
 * @return CostArray The resulting convolved cost array.
 */
constexpr auto min_plus_convolve(const CostArray &A, const CostArray &B)
    -> CostArray {
    auto res = CostArray();
    std::ranges::fill(res, std::numeric_limits<double>::infinity());

    for (const auto i : std::views::iota(0, MAX_WORK_RESOLUTION + 1)) {
        if (A[i] == std::numeric_limits<double>::infinity())
            continue;
        // We use a "push" DP approach here which is slightly more efficient
        // for sparse inputs (where many entries are infinity).
        for (const auto j : std::views::iota(0, MAX_WORK_RESOLUTION - i + 1)) {
            if (B[j] == std::numeric_limits<double>::infinity())
                continue;
            res[i + j] = std::min(res[i + j], A[i] + B[j]);
        }
    }
    return res;
}

/**
 * @brief Element-wise Minimum update.
 * target[i] = min(target[i], other[i])
 *
 * Used to merge paths in the Min-Plus Matrix Multiplication.
 *
 * @param target The array to update in-place.
 * @param other The array to compare against.
 */
constexpr auto element_wise_min(CostArray &target, const CostArray &other)
    -> void {
    for (auto [i, v] : std::views::enumerate(target))
        v = std::min(v, other[i]);
}

/**
 * @brief Finds the split indices (i, j) for reconstruction.
 *
 * Determines which contributions from left child (A[i]) and right child (B[j])
 * resulted in the target value (target_val) for total work (w_target).
 *
 * @param A The left child cost array.
 * @param B The right child cost array.
 * @param target_val The optimal cost value to match.
 * @param w_target The total work amount (i + j).
 * @return std::vector<int> List of valid 'i' indices (work amount for left
 * child).
 */
inline auto find_convolution_splits(const CostArray &A, const CostArray &B,
                                    const double target_val, const int w_target)
    -> std::vector<int> {
    auto res = std::vector<int>();
    for (const auto i :
         std::views::iota(0, std::min(w_target, MAX_WORK_RESOLUTION) + 1)) {
        const auto j = w_target - i;
        if (j > MAX_WORK_RESOLUTION)
            continue;
        if (A[i] == std::numeric_limits<double>::infinity() ||
            B[j] == std::numeric_limits<double>::infinity())
            continue;

        if (std::abs((A[i] + B[j]) - target_val) < 1e-9)
            res.push_back(i);
    }
    return res;
}

} // namespace scheduler
