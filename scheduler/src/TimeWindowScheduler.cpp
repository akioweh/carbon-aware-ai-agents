#include "TimeWindowScheduler.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace scheduler {

TimeWindowScheduler::TimeWindowScheduler(double work_unit_size)
    : work_unit_(work_unit_size), tree_(MAX_BLOCKS) {
    block_store_.resize(MAX_BLOCKS);
}

void TimeWindowScheduler::addBlock(const BlockData &block) {
    // Safety: if buffer is full, auto-pop
    if (tail_ - head_ >= MAX_BLOCKS)
        popBlock();

    size_t physical_idx = tail_ % MAX_BLOCKS;

    // Store block for updates
    block_store_[physical_idx] = block;

    // Create leaf matrix
    auto leaf = ProfileMatrix::fromBlock(block, work_unit_, PENALTY_WORK_P);

    // Update tree using point update (set)
    tree_.set(physical_idx, leaf);

    tail_++;
}

void TimeWindowScheduler::popBlock() {
    if (head_ < tail_)
        head_++;
}

auto TimeWindowScheduler::query(size_t start_offset, size_t end_offset,
                                double target_work) -> double {
    size_t l = head_ + start_offset;
    size_t r = head_ + end_offset; // Inclusive

    if (l >= tail_ || r >= tail_ || l > r)
        return -1.0;

    size_t phys_l = l % MAX_BLOCKS;
    size_t phys_r = r % MAX_BLOCKS;

    ProfileMatrix result;

    if (phys_l <= phys_r) {
        // Contiguous in buffer
        result = tree_.query(phys_l, phys_r + 1);
    } else {
        // Wrapped around
        auto part1 = tree_.query(phys_l, MAX_BLOCKS);
        auto part2 = tree_.query(0, phys_r + 1);
        result = part1 * part2;
    }

    // Extract min cost
    int w_idx = static_cast<int>(std::round(target_work));
    if (w_idx < 0 || w_idx > MAX_WORK_RESOLUTION)
        return -1.0;

    double min_cost = std::numeric_limits<double>::infinity();
    for (int u = 0; u < 2; ++u) {
        for (int v = 0; v < 2; ++v)
            min_cost = std::min(min_cost, result.data[u][v][w_idx]);
    }

    return min_cost == std::numeric_limits<double>::infinity() ? -1.0
                                                               : min_cost;
}

auto TimeWindowScheduler::getCostCurve(size_t start_offset,
                                       size_t end_offset) const
    -> std::vector<double> {
    size_t l = head_ + start_offset;
    size_t r = head_ + end_offset; // inclusive

    if (l >= tail_ || r >= tail_ || l > r) {
        return {};
    }

    size_t phys_l = l % MAX_BLOCKS;
    size_t phys_r = r % MAX_BLOCKS;

    ProfileMatrix result;

    if (phys_l <= phys_r) {
        result = tree_.query(phys_l, phys_r + 1);
    } else {
        auto part1 = tree_.query(phys_l, MAX_BLOCKS);
        auto part2 = tree_.query(0, phys_r + 1);
        result = part1 * part2;
    }

    std::vector<double> costs;
    costs.reserve(MAX_WORK_RESOLUTION + 1);

    for (int w = 0; w <= MAX_WORK_RESOLUTION; ++w) {
        double min_val = std::numeric_limits<double>::infinity();
        for (int u = 0; u < 2; ++u) {
            for (int v = 0; v < 2; ++v) {
                min_val = std::min(min_val, result.data[u][v][w]);
            }
        }
        costs.push_back(min_val);
    }
    return costs;
}

// Stateful Reservation
auto TimeWindowScheduler::reserve(size_t start_offset, size_t end_offset,
                                  double target_work)
    -> std::vector<InternalBlock> {

    std::vector<InternalBlock> out_blocks;

    size_t l = head_ + start_offset;
    size_t r = head_ + end_offset; // Inclusive

    if (l >= tail_ || r >= tail_ || l > r)
        return out_blocks;

    int w_idx = static_cast<int>(std::round(target_work));
    if (w_idx < 0 || w_idx > MAX_WORK_RESOLUTION)
        return out_blocks;

    size_t phys_l = l % MAX_BLOCKS;
    size_t phys_r = r % MAX_BLOCKS;

    std::vector<size_t> nodes;
    if (phys_l <= phys_r) {
        nodes = tree_.collect(phys_l, phys_r + 1);
    } else {
        auto part1 = tree_.collect(phys_l, MAX_BLOCKS);
        auto part2 = tree_.collect(0, phys_r + 1);
        nodes.reserve(part1.size() + part2.size());
        nodes.insert(nodes.end(), part1.begin(), part1.end());
        nodes.insert(nodes.end(), part2.begin(), part2.end());
    }

    if (nodes.empty())
        return out_blocks;

    // 1. Forward Pass
    std::vector<ProfileMatrix> prefixes;
    prefixes.reserve(nodes.size());
    prefixes.push_back(tree_.data[nodes[0]]);

    for (size_t i = 1; i < nodes.size(); ++i)
        prefixes.push_back(prefixes.back() * tree_.data[nodes[i]]);

    // 2. Determine global optimal end state and cost
    const auto &final_matrix = prefixes.back();
    double min_cost = std::numeric_limits<double>::infinity();
    int best_u = -1;
    int best_v = -1;

    for (int u = 0; u < 2; ++u) {
        for (int v = 0; v < 2; ++v) {
            if (final_matrix.data[u][v][w_idx] < min_cost) {
                min_cost = final_matrix.data[u][v][w_idx];
                best_u = u;
                best_v = v;
            }
        }
    }

    if (min_cost == std::numeric_limits<double>::infinity())
        return out_blocks;

    // 3. Backward Pass
    int current_w = w_idx;
    int current_out_state = best_v;
    int global_start_u = best_u;

    for (int i = static_cast<int>(nodes.size()) - 1; i >= 0; --i) {
        size_t node_idx = nodes[i];
        const auto &node_data = tree_.data[node_idx];

        if (i == 0) {
            bool res = reconstructNode(node_idx, current_w, global_start_u,
                                       current_out_state, out_blocks);
            if (!res)
                return {};
        } else {
            const auto &prev_prefix = prefixes[i - 1];
            bool found = false;

            for (int prev_w = 0; prev_w <= current_w; ++prev_w) {
                int node_w = current_w - prev_w;
                for (int state = 0; state < 2; ++state) {
                    double cost_prefix =
                        prev_prefix.data[global_start_u][state][prev_w];
                    double cost_node =
                        node_data.data[state][current_out_state][node_w];

                    if (cost_prefix ==
                            std::numeric_limits<double>::infinity() ||
                        cost_node == std::numeric_limits<double>::infinity())
                        continue;

                    double sum = cost_prefix + cost_node;
                    if (std::abs(
                            sum -
                            prefixes[i].data[global_start_u][current_out_state]
                                            [current_w]) < 1e-9) {
                        bool res =
                            reconstructNode(node_idx, node_w, state,
                                            current_out_state, out_blocks);
                        if (!res)
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

    std::ranges::reverse(out_blocks);

    // Optimized pull: only update from boundaries to avoid redundant O(K log N)
    // updates The ancestors of any node in the decomposition range [L, R] are
    // guaranteed to be ancestors of either leaf L or leaf R.
    if (phys_l <= phys_r) {
        tree_.pull(phys_l + tree_.N);
        if (phys_l != phys_r) {
            tree_.pull(phys_r + tree_.N);
        }
    } else {
        // Wrapped range: [phys_l, MAX_BLOCKS-1] and [0, phys_r]
        tree_.pull(phys_l + tree_.N);
        tree_.pull((MAX_BLOCKS - 1) + tree_.N);

        tree_.pull(0 + tree_.N);
        if (phys_r != 0) {
            tree_.pull(phys_r + tree_.N);
        }
    }

    return out_blocks;
}

bool TimeWindowScheduler::reconstructNode(
    size_t node_idx, int w_target, int state_in, int state_out,
    std::vector<InternalBlock> &out_blocks) {
    if (node_idx >= MAX_BLOCKS) {
        // Leaf Node
        size_t phys_idx = node_idx - MAX_BLOCKS;
        BlockData &block = block_store_[phys_idx];

        double added_work = 0;
        if (state_in == 0 && state_out == 1)
            added_work = (w_target * work_unit_) + PENALTY_WORK_P;
        else
            added_work = w_target * work_unit_;

        if (added_work > 1e-6)
            out_blocks.push_back({.timestamp = block.timestamp,
                                  .location = block.location_id,
                                  .additionalLoad = added_work});

        if (state_out == 1)
            block.initial_load += added_work;

        auto new_mat =
            ProfileMatrix::fromBlock(block, work_unit_, PENALTY_WORK_P);
        tree_.data[node_idx] = new_mat;

        return true;
    }

    size_t left_idx = 2 * node_idx;
    size_t right_idx = 2 * node_idx + 1;
    const auto &L = tree_.data[left_idx];
    const auto &R = tree_.data[right_idx];
    const auto &Self = tree_.data[node_idx];

    double target_cost = Self.data[state_in][state_out][w_target];

    for (int w_left = 0; w_left <= w_target; ++w_left) {
        int w_right = w_target - w_left;
        for (int mid_state = 0; mid_state < 2; ++mid_state) {
            double cost_l = L.data[state_in][mid_state][w_left];
            double cost_r = R.data[mid_state][state_out][w_right];

            if (cost_l == std::numeric_limits<double>::infinity() ||
                cost_r == std::numeric_limits<double>::infinity())
                continue;

            if (std::abs((cost_l + cost_r) - target_cost) < 1e-9) {
                // Visit Right then Left (Reverse order for efficient appending)
                // We record size to rollback if this path turns out to be
                // invalid due to precision issues deeper in the recursion.
                size_t snapshot = out_blocks.size();

                bool r2 = reconstructNode(right_idx, w_right, mid_state,
                                          state_out, out_blocks);
                if (r2) {
                    bool r1 = reconstructNode(left_idx, w_left, state_in,
                                              mid_state, out_blocks);
                    if (r1) {
                        // Both children successfully reconstructed
                        tree_.data[node_idx] = L * R;
                        return true;
                    }
                }

                // If we get here, one of the children failed. Rollback and try
                // next split.
                out_blocks.resize(snapshot);
            }
        }
    }

    return false;
}

} // namespace scheduler
