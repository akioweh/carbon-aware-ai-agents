#include "TimeWindowScheduler.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace scheduler {

TimeWindowScheduler::TimeWindowScheduler(const double work_unit_size)
    : work_unit_(work_unit_size), tree_(MAX_BLOCKS) {
    block_store_.resize(MAX_BLOCKS);
}

auto TimeWindowScheduler::addBlock(const BlockData &block) -> void {
    // Safety: if buffer is full, auto-pop
    if (tail_ - head_ >= MAX_BLOCKS)
        popBlock();
    auto physical_idx = size_t(tail_ % MAX_BLOCKS);
    block_store_[physical_idx] = block;
    auto leaf = ProfileMatrix::fromBlock(block, work_unit_, PENALTY_WORK_P);
    tree_.set(physical_idx, leaf);
    tail_++;
}

auto TimeWindowScheduler::popBlock() -> void {
    if (head_ < tail_)
        head_++;
}

auto TimeWindowScheduler::query(const size_t start_offset,
                                const size_t end_offset,
                                const double target_work) -> double {
    const auto l = head_ + start_offset;
    const auto r = head_ + end_offset; // Inclusive
    if (l >= tail_ || r >= tail_ || l > r)
        return -1.0;
    auto phys_l = size_t(l % MAX_BLOCKS);
    auto phys_r = size_t(r % MAX_BLOCKS);

    auto result = ProfileMatrix();

    if (phys_l <= phys_r)
        // Contiguous in buffer
        result = tree_.query(phys_l, phys_r + 1);
    else {
        // Wrapped around
        auto part1 = tree_.query(phys_l, MAX_BLOCKS);
        auto part2 = tree_.query(0, phys_r + 1);
        result = part1 * part2;
    }

    // Extract min cost
    auto w_idx = int(std::round(target_work));
    if (w_idx < 0 || w_idx > MAX_WORK_RESOLUTION)
        return -1.0;

    auto min_cost = std::numeric_limits<double>::infinity();
    for (auto u = 0; u < 2; ++u)
        for (auto v = 0; v < 2; ++v)
            min_cost = std::min(min_cost, result.data[u][v][w_idx]);

    return min_cost == std::numeric_limits<double>::infinity() ? -1.0
                                                               : min_cost;
}

auto TimeWindowScheduler::getCostCurve(const size_t start_offset,
                                       const size_t end_offset) const
    -> std::vector<double> {
    const auto l = head_ + start_offset;
    const auto r = head_ + end_offset; // inclusive
    if (l >= tail_ || r >= tail_ || l > r)
        return {};
    const auto phys_l = l % MAX_BLOCKS;
    const auto phys_r = r % MAX_BLOCKS;

    auto result = ProfileMatrix();

    if (phys_l <= phys_r)
        result = tree_.query(phys_l, phys_r + 1);
    else {
        auto part1 = tree_.query(phys_l, MAX_BLOCKS);
        auto part2 = tree_.query(0, phys_r + 1);
        result = part1 * part2;
    }

    auto costs = std::vector<double>();
    costs.reserve(MAX_WORK_RESOLUTION + 1);

    for (auto w = 0; w <= MAX_WORK_RESOLUTION; ++w) {
        auto min_val = std::numeric_limits<double>::infinity();
        for (auto u = 0; u < 2; ++u)
            for (auto v = 0; v < 2; ++v)
                min_val = std::min(min_val, result.data[u][v][w]);
        costs.push_back(min_val);
    }
    return costs;
}

auto TimeWindowScheduler::computeReservation(const size_t start_offset,
                                             const size_t end_offset,
                                             const double target_work)
    -> std::vector<InternalBlock> {
    const auto l = size_t(head_ + start_offset);
    const auto r = size_t(head_ + end_offset); // Inclusive
    if (l >= tail_ || r >= tail_ || l > r)
        return {};
    const auto w_idx = int(std::round(target_work));
    if (w_idx < 0 || w_idx > MAX_WORK_RESOLUTION)
        return {};
    const auto phys_l = size_t(l % MAX_BLOCKS);
    const auto phys_r = size_t(r % MAX_BLOCKS);

    auto nodes = std::vector<size_t>();
    if (phys_l <= phys_r)
        nodes = tree_.collect(phys_l, phys_r + 1);
    else {
        auto part1 = tree_.collect(phys_l, MAX_BLOCKS);
        auto part2 = tree_.collect(0, phys_r + 1);
        nodes.reserve(part1.size() + part2.size());
        nodes.insert(nodes.end(), part1.begin(), part1.end());
        nodes.insert(nodes.end(), part2.begin(), part2.end());
    }

    if (nodes.empty())
        return {};

    // 1. seg tree query but entire prefix "sum"
    auto prefixes = std::vector<ProfileMatrix>();
    prefixes.reserve(nodes.size());
    prefixes.push_back(tree_.data[nodes[0]]);

    for (const auto i : nodes | std::views::drop(1))
        prefixes.push_back(prefixes.back() * tree_.data[i]);

    // 2. Determine global optimal end state and cost
    const auto &final_matrix = prefixes.back();
    auto min_cost = std::numeric_limits<double>::infinity();
    auto best_u = -1;
    auto best_v = -1;

    for (auto u = 0; u < 2; ++u)
        for (auto v = 0; v < 2; ++v)
            if (final_matrix.data[u][v][w_idx] < min_cost) {
                min_cost = final_matrix.data[u][v][w_idx];
                best_u = u;
                best_v = v;
            }

    if (min_cost == std::numeric_limits<double>::infinity())
        return {};

    auto res = std::vector<InternalBlock>();

    // 3. reconstruction
    auto current_w = w_idx;
    auto current_out_state = best_v;
    auto global_start_u = best_u;

    for (auto i = nodes.size(); i--;) {
        auto node_idx = nodes[i];
        const auto &node_data = tree_.data[node_idx];

        if (i == 0) {
            if (!reconstructNode(node_idx, current_w, global_start_u,
                                 current_out_state, res))
                return {};
        } else {
            const auto &prev_prefix = prefixes[i - 1];
            auto found = false;

            for (auto prev_w = 0; prev_w <= current_w; ++prev_w) {
                auto node_w = (current_w - prev_w);
                for (auto state = 0; state < 2; ++state) {
                    auto cost_prefix =
                        prev_prefix.data[global_start_u][state][prev_w];
                    auto cost_node = double(
                        node_data.data[state][current_out_state][node_w]);

                    if (cost_prefix ==
                            std::numeric_limits<double>::infinity() ||
                        cost_node == std::numeric_limits<double>::infinity())
                        continue;

                    auto sum = cost_prefix + cost_node;
                    if (std::abs(
                            sum -
                            prefixes[i].data[global_start_u][current_out_state]
                                            [current_w]) < 1e-9) {
                        if (!reconstructNode(node_idx, node_w, state,
                                             current_out_state, res))
                            return {};

                        current_w = prev_w;
                        current_out_state = state;
                        found = true;
                        break;
                    }
                }
                if (found)
                    break;
            }
            if (!found)
                return {};
        }
    }

    std::ranges::reverse(res);
    return res;
}

auto TimeWindowScheduler::modifyLoad(const std::vector<InternalBlock> &blocks,
                                     const bool revert) -> void {
    if (blocks.empty())
        return;
    if (tail_ == head_)
        return;

    // Track the physical range of affected leaves to optimize the tree update.
    // We handle the wrap-around case by treating it as two possible ranges:
    // [min, max] or [min, N) U [0, max] But simplest is to just collect all
    // affected physical indices and batch-update.
    auto dirty_indices = std::vector<size_t>();
    dirty_indices.reserve(blocks.size());

    auto head_ts = block_store_[head_ % MAX_BLOCKS].timestamp;

    for (const auto &alloc : blocks) {
        const auto diff_mins = static_cast<long long>(
            std::chrono::duration_cast<std::chrono::minutes>(alloc.timestamp -
                                                             head_ts)
                .count());
        const auto offset =
            static_cast<long long>(diff_mins / 5); // Assumes 5 min grid

        if (offset < 0)
            continue;
        if (static_cast<size_t>(offset) >= (tail_ - head_))
            continue;

        const auto logical_idx = head_ + offset;
        const auto phys_idx = logical_idx % MAX_BLOCKS;

        // update load
        auto &block = block_store_[phys_idx];
        block.load += revert ? -alloc.additionalLoad : alloc.additionalLoad;

        // update leaf data
        auto new_mat =
            ProfileMatrix::fromBlock(block, work_unit_, PENALTY_WORK_P);
        tree_.data[phys_idx + MAX_BLOCKS] = new_mat;

        dirty_indices.push_back(phys_idx);
    }

    // 3. Batch Pull in O(K + log N)
    // To do this efficiently, we sort indices and move up the tree layer by
    // layer. Segment Tree layout: Leaves are [N, 2N-1]. Parent of k is k/2.
    if (dirty_indices.empty())
        return;

    // map to leaf indices then take parent
    for (auto &idx : dirty_indices)
        idx = (idx + MAX_BLOCKS) / 2;

    std::ranges::sort(dirty_indices);
    auto [new_last, end] = std::ranges::unique(dirty_indices);
    dirty_indices.erase(new_last, end);

    // Propagate up
    // We iterate while we have nodes to update.
    // In each step, we transform the current set of nodes to their parents.
    while (!dirty_indices.empty()) {
        auto parents = std::vector<size_t>();
        // this will over-allocate but that's fine
        parents.reserve(dirty_indices.size());

        auto last_par = -1UZ;
        for (auto p : dirty_indices) {
            tree_.data[p] = tree_.data[2 * p] * tree_.data[2 * p + 1];
            const auto par_idx = p / 2;
            if (par_idx != last_par)
                parents.push_back(par_idx);
            last_par = par_idx;
        }

        if (parents.size() == 1 && parents[0] == 0)
            break; // reached root; stop
        dirty_indices = std::move(parents);
    }
}

auto TimeWindowScheduler::reserve(const size_t start_offset,
                                  const size_t end_offset,
                                  const double target_work)
    -> std::vector<InternalBlock> {
    auto blocks = computeReservation(start_offset, end_offset, target_work);
    if (!blocks.empty())
        commitReservation(blocks);
    return blocks;
}

auto TimeWindowScheduler::commitReservation(
    const std::vector<InternalBlock> &blocks) -> void {
    modifyLoad(blocks);
}

auto TimeWindowScheduler::revertReservation(
    const std::vector<InternalBlock> &blocks) -> void {
    modifyLoad(blocks, true);
}

auto TimeWindowScheduler::reconstructNode(
    const size_t node_idx, const int w_target, const int state_in,
    const int state_out, std::vector<InternalBlock> &out_blocks) -> bool {
    if (node_idx >= MAX_BLOCKS) {
        // Leaf Node
        const auto phys_idx = node_idx - MAX_BLOCKS;
        const auto &block = block_store_[phys_idx]; // Read-only access now

        auto added_work = 0.;
        if (state_in == 0 && state_out == 1)
            added_work = (w_target * work_unit_) + PENALTY_WORK_P;
        else
            added_work = w_target * work_unit_;

        if (added_work > 1e-6)
            out_blocks.push_back({.timestamp = block.timestamp,
                                  .location = block.location_id,
                                  .additionalLoad = added_work});
        return true;
    }

    const auto left_idx = 2 * node_idx;
    const auto right_idx = (2 * node_idx) + 1;
    const auto &L = tree_.data[left_idx];
    const auto &R = tree_.data[right_idx];
    const auto &Self = tree_.data[node_idx];

    auto target_cost = double(Self.data[state_in][state_out][w_target]);

    // Try both possible intermediate states (Inactive=0, Active=1)
    for (auto mid_state = 0; mid_state < 2; ++mid_state) {
        // Find all (w_left, w_right) combinations that sum to target_cost via
        // mid_state using the helper from AlgoUtils
        auto splits = find_convolution_splits(L.data[state_in][mid_state],
                                              R.data[mid_state][state_out],
                                              target_cost, w_target);

        for (const auto w_left : splits) {
            const auto w_right = w_target - w_left;
            const auto snapshot = out_blocks.size();

            // right the left due to reverse order
            if (reconstructNode(right_idx, w_right, mid_state, state_out,
                                out_blocks) &&
                reconstructNode(left_idx, w_left, state_in, mid_state,
                                out_blocks)) {
                return true;
            }
            // rollback
            out_blocks.resize(snapshot);
        }
    }

    return false;
}

} // namespace scheduler
