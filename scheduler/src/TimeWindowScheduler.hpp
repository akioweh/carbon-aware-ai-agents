#pragma once

#include "AlgoUtils.hpp"
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
 * @brief Startup Penalty (P) expressed in equivalent work units.
 *
 * When switching from Inactive (0) to Active (1), the system "pays" this cost.
 * In the Min-Plus model, we represent this by reducing the effective Net Work:
 * NetWork = PhysicalWork - P.
 *
 * Example: If P=20, and we do 50 units of physical work, only 30 units of
 * useful Net Work are produced. The 20 units are "lost" to startup overhead.
 */
constexpr double PENALTY_WORK_P = 20.0;
constexpr size_t MAX_BLOCKS = 16384;

/**
 * @struct BlockData
 * @brief Stores the state of a single time block.
 */
struct BlockData {
    double capacity;
    double load;
    double greenness;
    std::string location_id;
    std::chrono::system_clock::time_point timestamp;
};

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
                std::ranges::fill(data[u][v],
                                  std::numeric_limits<double>::infinity());

        // Identity diagonals: State preserved with 0 work/cost
        data[0][0][0] = 0.0;
        data[1][1][0] = 0.0;
    }

    /**
     * @brief Constructs a leaf matrix from a single block.
     * Computes costs for all possible work levels, applying startup penalties.
     */
    static constexpr auto fromBlock(const BlockData &block, double work_unit,
                                    const double penalty_work)
        -> ProfileMatrix {
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
        const auto available = std::max(block.capacity - block.load, 0.);
        const auto max_phys_idx = static_cast<int>(available / work_unit);

        for (int w_idx = 1;
             w_idx <= max_phys_idx && w_idx <= MAX_WORK_RESOLUTION; ++w_idx) {
            const auto w_val = w_idx * work_unit;
            // Linear cost model: (Load / Capacity) / Greenness
            // Marginal cost of adding w_val
            const auto cost =
                ((block.load + w_val) / block.capacity /
                 std::max(block.greenness, 0.01)) -
                (block.load / block.capacity / std::max(block.greenness, 0.01));

            // Case u=1 (Active -> Active): No penalty
            m.data[1][1][w_idx] = std::min(m.data[1][1][w_idx], cost);

            // Case u=0 (Inactive -> Active): Penalty P applies.
            // Net Work = Physical Work - Penalty.
            const auto net_work = w_val - penalty_work;
            if (net_work >= 0) {
                const auto net_idx =
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
        auto res = ProfileMatrix{};
        // initialize everything to infinity (overriding default identity
        // initialization)
        for (auto &row : res.data)
            for (auto &entry : row)
                std::ranges::fill(entry,
                                  std::numeric_limits<double>::infinity());

        for (int u = 0; u < 2; ++u) {     // Start state
            for (int v = 0; v < 2; ++v) { // End state
                // Path via Inactive (k=0)
                // L[u][0] * R[0][v]
                auto path0 = min_plus_convolve(L.data[u][0], R.data[0][v]);

                // Path via Active (k=1)
                // L[u][1] * R[1][v]
                auto path1 = min_plus_convolve(L.data[u][1], R.data[1][v]);

                element_wise_min(path0, path1);
                res.data[u][v] = path0;
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

    /**
     * @brief Adds a new time block to the rolling window.
     *
     * If the internal buffer is full (MAX_BLOCKS), the oldest block is
     * automatically popped to make room.
     *
     * @param block The block data (capacity, load, greenness, etc.)
     */
    auto addBlock(const BlockData &block) -> void;

    /**
     * @brief Removes the oldest block from the window.
     *
     * Advances the 'head' pointer, effectively shifting the window forward in
     * time.
     */
    auto popBlock() -> void;

    /**
     * @brief Queries the minimum cost for a specific work amount in a time
     * range.
     *
     * Does not modify state.
     *
     * @param start_offset Index relative to the current head (0 = now).
     * @param end_offset Index relative to the current head (inclusive).
     * @param target_work The amount of work to schedule.
     * @return double The minimum cost (SCI score), or -1.0 if infeasible.
     */
    auto query(size_t start_offset, size_t end_offset, double target_work)
        -> double;

    /**
     * @brief Retrieves the full cost profile for a time range.
     *
     * Used by the MultiLocationScheduler to aggregate costs across locations.
     *
     * @param start_offset Index relative to the current head.
     * @param end_offset Index relative to the current head.
     * @return std::vector<double> A vector where index 'i' is the cost for 'i'
     * work units.
     */
    [[nodiscard]] auto getCostCurve(size_t start_offset,
                                    size_t end_offset) const
        -> std::vector<double>;

    /**
     * @brief Orchestrates the full reservation process: Compute + Commit.
     *
     * This is the primary method for scheduling jobs. It calculates the optimal
     * placement and immediately updates the internal state to reflect the
     * increased load.
     *
     * @param start_offset Index relative to the current head.
     * @param end_offset Index relative to the current head.
     * @param target_work The amount of work to schedule.
     * @return std::vector<InternalBlock> The list of allocated blocks with
     * their specific load.
     */
    auto reserve(size_t start_offset, size_t end_offset, double target_work)
        -> std::vector<InternalBlock>;

    /**
     * @brief Computes the optimal allocation plan WITHOUT modifying state.
     *
     * Performs the "Query" phase of the scheduling, reconstructing the path
     * to find exactly where work should be placed.
     *
     * @return std::vector<InternalBlock> The proposed allocation plan.
     */
    auto computeReservation(size_t start_offset, size_t end_offset,
                            double target_work) -> std::vector<InternalBlock>;

    /**
     * @brief Applies a previously computed allocation to the state.
     *
     * Updates the Segment Tree with the new loads. This is an O(K + log N)
     * operation using the optimized batch update.
     *
     * @param blocks The blocks to commit (usually from computeReservation).
     */
    auto commitReservation(const std::vector<InternalBlock> &blocks) -> void;

    /**
     * @brief Reverses a previously computed allocation.
     *
     * Effectively "deletes" a job by subtracting its load from the tree.
     *
     * @param blocks The blocks to revert.
     */
    auto revertReservation(const std::vector<InternalBlock> &blocks) -> void;

  private:
    double work_unit_;
    size_t head_ = 0; // Logical index of the first valid block
    size_t tail_ = 0; // Logical index of the next slot

    SchedulerTree tree_;

    // Store block data for updates
    std::vector<BlockData> block_store_;

    auto updateTree(size_t logical_index, const BlockData &block) -> void;

    // Recursive reconstruction and update
    // Returns true if the node was successfully reconstructed
    auto reconstructNode(size_t node_idx, int w_target, int state_in,
                         int state_out, std::vector<InternalBlock> &out_blocks)
        -> bool;

    auto modifyLoad(const std::vector<InternalBlock> &blocks,
                    bool revert = false) -> void;
};
} // namespace scheduler
