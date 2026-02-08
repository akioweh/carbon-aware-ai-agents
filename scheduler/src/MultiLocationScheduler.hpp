#pragma once
#include "TimeWindowScheduler.hpp"
#include <map>
#include <string>
#include <vector>

namespace scheduler {

/**
 * @class MultiLocationScheduler
 * @brief Orchestrates multiple TimeWindowScheduler instances to solve the
 * multi-location resource allocation problem.
 *
 * It aggregates the cost curves from each location and uses a Knapsack-style
 * Dynamic Programming approach to find the globally optimal distribution of
 * work across locations.
 */
class MultiLocationScheduler {
  public:
    explicit MultiLocationScheduler(double work_unit_size);

    /**
     * @brief Adds a block to a specific location's timeline.
     *
     * If the location doesn't exist, a new TimeWindowScheduler is created for
     * it.
     *
     * @param location_id Unique identifier for the datacenter/location.
     * @param block The block data to append.
     */
    auto addBlock(const std::string &location_id, const BlockData &block)
        -> void;

    /**
     * @brief Rolls the window for ALL managed locations.
     *
     * This assumes that all locations are synchronized to the same time grid.
     * Calling this advances the head of every internal TimeWindowScheduler.
     */
    auto popBlock() -> void;

    /**
     * @brief Returns the global minimum cost to schedule 'target_work' across
     * all locations.
     *
     * @param start_offset Index relative to the current head.
     * @param end_offset Index relative to the current head.
     * @param target_work Total work amount to be distributed.
     * @return double The global minimum SCI score, or -1.0 if infeasible.
     */
    auto query(size_t start_offset, size_t end_offset, double target_work)
        -> double;

    /**
     * @brief Reserves resources optimally across multiple locations.
     *
     * 1. Aggregates cost curves from all locations.
     * 2. Solves the global resource distribution problem (Knapsack-like).
     * 3. Computes specific schedules for each location based on the
     * distribution.
     * 4. Commits the changes to all underlying schedulers.
     *
     * @return std::vector<InternalBlock> List of all allocated blocks across
     * all locations.
     */
    auto reserve(size_t start_offset, size_t end_offset, double target_work)
        -> std::vector<InternalBlock>;

    /**
     * @brief Computes the optimal allocation plan WITHOUT modifying state.
     *
     * Useful for "dry run" or "what-if" scenarios.
     */
    auto computeReservation(size_t start_offset, size_t end_offset,
                            double target_work) -> std::vector<InternalBlock>;

    /**
     * @brief Applies a previously computed allocation to the state.
     *
     * Splits the block list by location and delegates to the respective
     * TimeWindowScheduler.
     */
    auto commitReservation(const std::vector<InternalBlock> &blocks) -> void;

    /**
     * @brief Reverses a previously computed allocation (deletion).
     */
    auto revertReservation(const std::vector<InternalBlock> &blocks) -> void;

  private:
    double work_unit_;
    std::map<std::string, TimeWindowScheduler> schedulers_;

    // Helper: Solves the global Knapsack problem.
    // Returns pair { min_cost, map<location_id, allocated_work_index> }
    // If infeasible, returns { infinity, {} }
    auto solveGlobal(size_t start_offset, size_t end_offset, int target_w_idx)
        -> std::pair<double, std::map<std::string, int>>;
};

} // namespace scheduler
