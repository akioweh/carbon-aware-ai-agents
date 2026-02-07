#pragma once

#include "SegmentTree.hpp"
#include "structs/SchedulerOutput.hpp"
#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <functional>
#include <limits>
#include <string>
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
constexpr double PENALTY_WORK_P = 20.0;
constexpr size_t MAX_BLOCKS = 16384;

/**
 * @struct BlockData
 * @brief Stores the state of a single time block.
 */
struct BlockData {
    double capacity;
    double initial_load;
    double greenness;
    std::string location_id;
    std::chrono::system_clock::time_point timestamp;
};

// Use std::array for Structural Type support (required for NTTP in SegmentTree)
using CostArray = std::array<double, MAX_WORK_RESOLUTION + 1>;

/**
 * @struct ProfileMatrix
 * @brief Represents the Cost-to-NetWork function for a time interval.
 *
 * A 2x2 matrix of cost arrays, where dimensions represent the boundary states:
 * 0: Inactive (Work = 0)
 * 1: Active (Work > 0)
 *
 * entry[u][v][w] is the min cost to achieve Net Work 'w' starting in state 'u'
 * and ending in state 'v'.
 */
struct ProfileMatrix {
    std::array<std::array<CostArray, 2>, 2> data;

    // Default constructor: Initializes to Identity for Min-Plus multiplication.
    // Identity: Cost 0 for Work 0 if states match, Infinity otherwise.
    constexpr ProfileMatrix() : data{} {
        // Initialize to infinity
        for (int u = 0; u < 2; ++u)
            for (int v = 0; v < 2; ++v)
                for (int w = 0; w <= MAX_WORK_RESOLUTION; ++w)
                    data[u][v][w] = std::numeric_limits<double>::infinity();

        // Identity diagonals: State preserved with 0 work/cost
        data[0][0][0] = 0.0;
        data[1][1][0] = 0.0;
    }

    /**
     * @brief Constructs a leaf matrix from a single block.
     * Computes costs for all possible work levels, applying startup penalties.
     */
    static constexpr auto fromBlock(const BlockData &block, double work_unit,
                                    double penalty_work) -> ProfileMatrix {
        ProfileMatrix m;
        // Reset to all-infinity to override default identity diagonals where
        // inappropriate (Though strictly, we only need to set valid entries)

        // 1. State 0 (Inactive): Only valid for w=0.
        // [0][0][0] is 0 (from default).
        // [1][0][0] (Active->Inactive) is 0 cost, 0 work.
        m.data[1][0][0] = 0.0;
        // [1][1][0] (Active->Active with 0 work) is invalid, as Active implies
        // w > 0.
        m.data[1][1][0] = std::numeric_limits<double>::infinity();

        // 2. State 1 (Active): Iterate valid physical work
        double available = block.capacity - block.initial_load;
        available = std::max(available, 0.);

        int max_phys_idx = static_cast<int>(available / work_unit);

        for (int w_idx = 1;
             w_idx <= max_phys_idx && w_idx <= MAX_WORK_RESOLUTION; ++w_idx) {
            double w_val = w_idx * work_unit;
            // Linear cost model: (Load / Capacity) / Greenness
            // Marginal cost of adding w_val
            double cost = (block.initial_load + w_val) / block.capacity /
                              std::max(block.greenness, 0.01) -
                          (block.initial_load / block.capacity /
                           std::max(block.greenness, 0.01));

            // Case u=1 (Active -> Active): No penalty. Net Work = Physical
            // Work.
            m.data[1][1][w_idx] = std::min(m.data[1][1][w_idx], cost);

            // Case u=0 (Inactive -> Active): Penalty P applies.
            // Net Work = Physical Work - Penalty.
            double net_work = w_val - penalty_work;
            if (net_work >= 0) {
                int net_idx =
                    static_cast<int>(std::round(net_work / work_unit));
                if (net_idx >= 0 && net_idx <= MAX_WORK_RESOLUTION)
                    m.data[0][1][net_idx] =
                        std::min(m.data[0][1][net_idx], cost);
            }
        }
        return m;
    }

    /**
     * @brief Min-Plus Matrix Multiplication.
     * Combines two time intervals (L then R).
     * T[u][v][w] = min_{k, w1+w2=w} (L[u][k][w1] + R[k][v][w2])
     */
    friend constexpr auto operator*(const ProfileMatrix &L,
                                    const ProfileMatrix &R) -> ProfileMatrix {
        ProfileMatrix res;
        // Reset accumulator to infinity
        for (int u = 0; u < 2; ++u)
            for (int v = 0; v < 2; ++v)
                for (int w = 0; w <= MAX_WORK_RESOLUTION; ++w)
                    res.data[u][v][w] = std::numeric_limits<double>::infinity();

        // Iterate boundary states
        for (int u = 0; u < 2; ++u) {     // Start state
            for (int v = 0; v < 2; ++v) { // End state
                // Try split state k (Inactive=0, Active=1)

                // k=0 (Mid state Inactive)
                const auto &A0 = L.data[u][0];
                const auto &B0 = R.data[0][v];
                auto &C = res.data[u][v];

                // Convolution
                for (int i = 0; i <= MAX_WORK_RESOLUTION; ++i) {
                    if (A0[i] == std::numeric_limits<double>::infinity())
                        continue;
                    int max_j = MAX_WORK_RESOLUTION - i;
                    for (int j = 0; j <= max_j; ++j) {
                        if (B0[j] == std::numeric_limits<double>::infinity())
                            continue;
                        double val = A0[i] + B0[j];
                        C[i + j] = std::min(val, C[i + j]);
                    }
                }

                // k=1 (Mid state Active)
                const auto &A1 = L.data[u][1];
                const auto &B1 = R.data[1][v];

                for (int i = 0; i <= MAX_WORK_RESOLUTION; ++i) {
                    if (A1[i] == std::numeric_limits<double>::infinity())
                        continue;
                    int max_j = MAX_WORK_RESOLUTION - i;
                    for (int j = 0; j <= max_j; ++j) {
                        if (B1[j] == std::numeric_limits<double>::infinity())
                            continue;
                        double val = A1[i] + B1[j];
                        C[i + j] = std::min(val, C[i + j]);
                    }
                }
            }
        }
        return res;
    }

    auto operator==(const ProfileMatrix &) const -> bool = default;
};

// Define Identity as a constexpr variable for the template
constexpr ProfileMatrix IDENTITY_MATRIX = ProfileMatrix();

// The Segment Tree Type using Point Update Range Query (PURQ)
using SchedulerTree =
    PURQ<ProfileMatrix, IDENTITY_MATRIX, std::multiplies<ProfileMatrix>{}>;

/**
 * @class TimeWindowScheduler
 * @brief Handles rolling-window scheduling with "Reserve" capability.
 *
 * Maintains a fixed-size buffer of blocks mapped to a Segment Tree.
 * Supports efficient queries and updates for optimal resource allocation
 * considering non-convex penalties (startup costs).
 */
class TimeWindowScheduler {
  public:
    explicit TimeWindowScheduler(double work_unit_size);

    // move-only because expensive ass structure
    TimeWindowScheduler(const TimeWindowScheduler &) = delete;
    auto operator=(const TimeWindowScheduler &)
        -> TimeWindowScheduler & = delete;
    TimeWindowScheduler(TimeWindowScheduler &&) = default;
    auto operator=(TimeWindowScheduler &&) -> TimeWindowScheduler & = default;

    void addBlock(const BlockData &block);
    void popBlock(); // Rolls the window

    // Returns the min cost for target_work within range [start_offset,
    // end_offset] Returns -1 if infeasible
    auto query(size_t start_offset, size_t end_offset, double target_work)
        -> double;

    // Allocates/Reserves the optimal work distribution.
    // Modifies the underlying blocks' load.
    // Returns the scheduled blocks if successful, empty if infeasible.
    auto reserve(size_t start_offset, size_t end_offset, double target_work)
        -> std::vector<InternalBlock>;

  private:
    double work_unit_;
    size_t head_ = 0; // Logical index of the first valid block
    size_t tail_ = 0; // Logical index of the next slot

    SchedulerTree tree_;

    // Store block data for updates
    std::vector<BlockData> block_store_;

    void updateTree(size_t logical_index, const BlockData &block);

    // Recursive reconstruction and update
    // Returns true if the node was successfully reconstructed
    auto reconstructNode(size_t node_idx, int w_target, int state_in,
                         int state_out, std::vector<InternalBlock> &out_blocks)
        -> bool;
};
} // namespace scheduler
