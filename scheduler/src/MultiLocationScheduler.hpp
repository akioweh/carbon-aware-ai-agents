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

    // Adds a block to a specific location's timeline.
    // If the location doesn't exist, it is created.
    void addBlock(const std::string &location_id, const BlockData &block);

    // Rolls the window for ALL managed locations.
    // Assumes synchronized time steps across locations.
    void popBlock();

    // Returns the global minimum cost to schedule 'target_work' across all
    // locations within the specified time offset range. Returns -1 if
    // infeasible.
    auto query(size_t start_offset, size_t end_offset, double target_work)
        -> double;

    // Reserves resources optimally across locations.
    // Performs the global optimization, then commits specific reservations to
    // each underlying TimeWindowScheduler. Returns a list of all allocated
    // blocks.
    auto reserve(size_t start_offset, size_t end_offset, double target_work)
        -> std::vector<InternalBlock>;

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
