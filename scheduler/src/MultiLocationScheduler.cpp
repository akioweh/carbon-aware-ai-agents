#include "MultiLocationScheduler.hpp"
#include <future>
#include <limits>
#include <vector>

namespace scheduler {

MultiLocationScheduler::MultiLocationScheduler(double work_unit_size)
    : work_unit_(work_unit_size) {}

void MultiLocationScheduler::addBlock(const std::string &location_id,
                                      const BlockData &block) {
    auto it = schedulers_.find(location_id);
    if (it == schedulers_.end()) {
        it = schedulers_
                 .emplace(std::piecewise_construct,
                          std::forward_as_tuple(location_id),
                          std::forward_as_tuple(work_unit_))
                 .first;
    }
    it->second.addBlock(block);
}

void MultiLocationScheduler::popBlock() {
    for (auto &[_, sched] : schedulers_) {
        sched.popBlock();
    }
}

auto MultiLocationScheduler::query(size_t start_offset, size_t end_offset,
                                   double target_work) -> double {
    int target_w_idx = static_cast<int>(std::round(target_work / work_unit_));
    // Validate target work
    if (target_w_idx < 0 || target_w_idx > MAX_WORK_RESOLUTION) {
        return -1.0;
    }

    auto [cost, _] = solveGlobal(start_offset, end_offset, target_w_idx);
    return cost == std::numeric_limits<double>::infinity() ? -1.0 : cost;
}

auto MultiLocationScheduler::reserve(size_t start_offset, size_t end_offset,
                                     double target_work)
    -> std::vector<InternalBlock> {
    int target_w_idx = static_cast<int>(std::round(target_work / work_unit_));
    if (target_w_idx < 0 || target_w_idx > MAX_WORK_RESOLUTION) {
        return {};
    }

    auto [cost, distribution] =
        solveGlobal(start_offset, end_offset, target_w_idx);

    if (cost == std::numeric_limits<double>::infinity()) {
        return {};
    }

    std::vector<InternalBlock> all_blocks;
    for (const auto &[loc_id, w_idx] : distribution) {
        if (w_idx > 0) {
            double w = w_idx * work_unit_;
            auto blocks =
                schedulers_.at(loc_id).reserve(start_offset, end_offset, w);
            all_blocks.insert(all_blocks.end(), blocks.begin(), blocks.end());
        }
    }
    return all_blocks;
}

auto MultiLocationScheduler::solveGlobal(size_t start_offset, size_t end_offset,
                                         int target_w_idx)
    -> std::pair<double, std::map<std::string, int>> {

    if (schedulers_.empty()) {
        return {std::numeric_limits<double>::infinity(), {}};
    }

    // parallel per-location cost curve retrieval
    std::vector<std::string> loc_ids;
    loc_ids.reserve(schedulers_.size());

    using Curve = std::vector<double>;
    std::vector<std::future<Curve>> futures;
    futures.reserve(schedulers_.size());

    for (auto &[id, sched] : schedulers_) {
        loc_ids.push_back(id);
        futures.push_back(std::async(
            std::launch::async,
            [&sched, start_offset, end_offset]() -> std::vector<double> {
                return sched.getCostCurve(start_offset, end_offset);
            }));
    }

    std::vector<Curve> curves;
    curves.reserve(schedulers_.size());

    for (auto &f : futures) {
        auto curve = f.get();
        if (curve.empty()) {
            return {std::numeric_limits<double>::infinity(), {}};
        }
        curves.push_back(std::move(curve));
    }

    // dp[w] = min cost for w total work
    // parent[i][w] = work allocated to location i
    std::vector<double> dp(MAX_WORK_RESOLUTION + 1,
                           std::numeric_limits<double>::infinity());
    dp[0] = 0.0;

    // to reconstruct, we need a table: parent[loc_index][current_total_work] ->
    // work_for_this_loc
    std::vector<std::vector<int>> parent(
        loc_ids.size(), std::vector<int>(MAX_WORK_RESOLUTION + 1, 0));

    for (int w = 0; w <= MAX_WORK_RESOLUTION; ++w) {
        dp[w] = curves[0][w];
        parent[0][w] = w;
    }
    for (size_t i = 1; i < loc_ids.size(); ++i) {
        std::vector<double> next_dp(MAX_WORK_RESOLUTION + 1,
                                    std::numeric_limits<double>::infinity());
        const auto &cost_curve = curves[i];

        for (int w = 0; w <= MAX_WORK_RESOLUTION; ++w) {
            // try all split points k (work for current location i)
            // w - k (work for previous locations 0..i-1)
            for (int k = 0; k <= w; ++k) {
                double prev_cost = dp[w - k];
                double curr_cost = cost_curve[k];

                if (prev_cost == std::numeric_limits<double>::infinity() ||
                    curr_cost == std::numeric_limits<double>::infinity())
                    continue;

                if (prev_cost + curr_cost < next_dp[w]) {
                    next_dp[w] = prev_cost + curr_cost;
                    parent[i][w] = k;
                }
            }
        }
        dp = std::move(next_dp);
    }

    double min_total_cost = dp[target_w_idx];
    if (min_total_cost == std::numeric_limits<double>::infinity()) {
        return {min_total_cost, {}};
    }

    // reconstruction
    std::map<std::string, int> distribution;
    int current_w = target_w_idx;

    for (int i = static_cast<int>(loc_ids.size()) - 1; i >= 0; --i) {
        int allocated = parent[i][current_w];
        distribution[loc_ids[i]] = allocated;
        current_w -= allocated;
    }

    return {min_total_cost, distribution};
}

} // namespace scheduler
