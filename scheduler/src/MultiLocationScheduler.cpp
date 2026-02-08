#include "MultiLocationScheduler.hpp"
#include "AlgoUtils.hpp"
#include <future>
#include <limits>
#include <vector>

namespace scheduler {

MultiLocationScheduler::MultiLocationScheduler(double work_unit_size)
    : work_unit_(work_unit_size) {}

auto MultiLocationScheduler::addBlock(const std::string &location_id,
                                      const BlockData &block) -> void {
    auto it = schedulers_.find(location_id);
    if (it == schedulers_.end())
        it = schedulers_
                 .emplace(std::piecewise_construct,
                          std::forward_as_tuple(location_id),
                          std::forward_as_tuple(work_unit_))
                 .first;
    it->second.addBlock(block);
}

auto MultiLocationScheduler::popBlock() -> void {
    std::ranges::for_each(schedulers_ | std::views::values,
                          &decltype(schedulers_)::mapped_type::popBlock);
}

auto MultiLocationScheduler::query(const size_t start_offset,
                                   const size_t end_offset,
                                   const double target_work) -> double {
    auto target_w_idx = static_cast<int>(std::round(target_work / work_unit_));
    if (target_w_idx < 0 || target_w_idx > MAX_WORK_RESOLUTION)
        return -1.0;

    auto [cost, _] = solveGlobal(start_offset, end_offset, target_w_idx);
    return cost == std::numeric_limits<double>::infinity() ? -1.0 : cost;
}

auto MultiLocationScheduler::reserve(const size_t start_offset,
                                     const size_t end_offset,
                                     const double target_work)
    -> std::vector<InternalBlock> {
    auto blocks = computeReservation(start_offset, end_offset, target_work);
    if (!blocks.empty())
        commitReservation(blocks);
    return blocks;
}

auto MultiLocationScheduler::computeReservation(size_t start_offset,
                                                size_t end_offset,
                                                double target_work)
    -> std::vector<InternalBlock> {
    auto target_w_idx = int(std::round(target_work / work_unit_));
    if (target_w_idx < 0 || target_w_idx > MAX_WORK_RESOLUTION)
        return {};

    auto [cost, distribution] =
        solveGlobal(start_offset, end_offset, target_w_idx);

    if (cost == std::numeric_limits<double>::infinity())
        return {};

    auto all_blocks = std::vector<InternalBlock>();
    for (const auto &[loc_id, w_idx] : distribution) {
        if (w_idx <= 0)
            continue;
        const auto blocks = schedulers_.at(loc_id).computeReservation(
            start_offset, end_offset, w_idx * work_unit_);
        // all_blocks.insert(all_blocks.end(), blocks.begin(), blocks.end());
        all_blocks.insert_range(all_blocks.end(), blocks);
    }
    return all_blocks;
}

auto MultiLocationScheduler::commitReservation(
    const std::vector<InternalBlock> &blocks) -> void {
    auto grouped = std::map<std::string, std::vector<InternalBlock>>();
    for (const auto &block : blocks)
        grouped[block.location].push_back(block);

    for (auto &[loc, sub_blocks] : grouped)
        if (schedulers_.contains(loc))
            schedulers_.at(loc).commitReservation(sub_blocks);
}

auto MultiLocationScheduler::revertReservation(
    const std::vector<InternalBlock> &blocks) -> void {
    auto grouped = std::map<std::string, std::vector<InternalBlock>>();
    for (const auto &block : blocks)
        grouped[block.location].push_back(block);

    for (auto &[loc, sub_blocks] : grouped)
        if (schedulers_.contains(loc))
            schedulers_.at(loc).revertReservation(sub_blocks);
}

auto MultiLocationScheduler::solveGlobal(const size_t start_offset,
                                         const size_t end_offset,
                                         const int target_w_idx)
    -> std::pair<double, std::map<std::string, int>> {
    if (schedulers_.empty())
        return {std::numeric_limits<double>::infinity(), {}};

    // parallel per-location cost curve retrieval
    auto loc_ids = std::vector<std::string>();
    loc_ids.reserve(schedulers_.size());

    using Curve = std::vector<double>;
    auto futures = std::vector<std::future<Curve>>();
    futures.reserve(schedulers_.size());

    for (auto &[id, sched] : schedulers_) {
        loc_ids.push_back(id);
        futures.push_back(std::async(
            std::launch::async,
            [&sched, start_offset, end_offset]() -> std::vector<double> {
                return sched.getCostCurve(start_offset, end_offset);
            }));
    }

    auto location_curves = std::vector<CostArray>();
    location_curves.reserve(schedulers_.size());

    for (auto &f : futures) {
        auto curve = f.get();
        if (curve.empty())
            return {std::numeric_limits<double>::infinity(), {}};

        // Convert vector to CostArray
        auto arr = CostArray();
        std::ranges::fill(arr, std::numeric_limits<double>::infinity());
        const auto n = std::min(curve.size(), arr.size());
        std::ranges::copy(curve.begin(), curve.begin() + n, arr.begin());
        location_curves.push_back(arr);
    }

    // dp_prefixes stores the cumulative cost curve after including locations
    // 0..i Used for backtracking.
    auto dp_prefixes = std::vector<CostArray>();
    dp_prefixes.reserve(loc_ids.size());
    dp_prefixes.push_back(location_curves[0]);

    for (auto i = size_t(1); i < location_curves.size(); ++i)
        dp_prefixes.push_back(
            min_plus_convolve(dp_prefixes.back(), location_curves[i]));

    const auto &final_dp = dp_prefixes.back();
    auto min_total_cost = final_dp[target_w_idx];

    if (min_total_cost == std::numeric_limits<double>::infinity())
        return {min_total_cost, {}};

    // reconstruction
    auto distribution = std::map<std::string, int>();
    auto current_w = target_w_idx;

    for (auto i = loc_ids.size(); i--;) {
        if (i == 0) {
            // Last location (first in list) takes the remainder
            distribution[loc_ids[0]] = current_w;
        } else {
            const auto &prev_dp = dp_prefixes[i - 1];
            const auto &curr_loc_curve = location_curves[i];

            // Find k (allocation for this location) such that prev_dp[current_w
            // - k] + curr_loc_curve[k] == total_cost We know total_cost is
            // dp_prefixes[i][current_w]
            auto target = double(dp_prefixes[i][current_w]);

            auto splits = find_convolution_splits(prev_dp, curr_loc_curve,
                                                  target, current_w);

            if (!splits.empty()) {
                // Just take the first valid split.
                // Since this is the top-level aggregation (no recursion failure
                // possible like in SegTree), any valid mathematical split is a
                // valid schedule distribution.
                auto k = int(current_w - splits[0]); // splits returns 'i'
                                                     // (prev_dp index), so k
                                                     // (curr index) is w - i

                distribution[loc_ids[i]] = k;
                current_w -= k;
            } else {
                // should not happen... unless float inacccuracies
                return {std::numeric_limits<double>::infinity(), {}};
            }
        }
    }

    return {min_total_cost, distribution};
}

} // namespace scheduler
