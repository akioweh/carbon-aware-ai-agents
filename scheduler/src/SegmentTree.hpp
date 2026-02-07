#pragma once
#include <algorithm>
#include <bit>
#include <cassert>
#include <concepts>
#include <iterator>
#include <limits>
#include <ranges>
#include <type_traits>
#include <vector>

template <typename F, typename U, typename V, typename R>
concept binary_func = std::is_invocable_r_v<R, F, U, V>;

template <typename T = long long, // output/base type
          T Default =
              std::numeric_limits<T>::min(), // identity for query (e.g., 0
                                             // for sum, -INF for max)
          binary_func<T, T, T> auto Func = [](T a, T b) -> auto {
              return std::max(a, b);
          } // fold function (default: max)
          >
struct PURQ {
    size_t N;
    size_t H;
    std::vector<T> data;

    PURQ(const size_t n) : N(n), H(std::bit_width(n)), data(2 * n, Default) {}

    // construct from range/iterator
    template <std::ranges::input_range R>
        requires(std::same_as<std::ranges::range_value_t<R>, T> &&
                 std::ranges::sized_range<R>)
    explicit PURQ(R &&seq)
        : N(std::ranges::size(seq)), H(std::bit_width(std::ranges::size(seq))) {
        data.resize(2 * N);
        std::ranges::copy(seq, data.begin() + N);
        for (auto i = N; i--;)
            data[i] = Func(data[2 * i], data[2 * i + 1]);
    }

    // calculates the length of node
    [[nodiscard]] auto node_size(const size_t _i) const -> size_t {
        if (_i >= N)
            return 1ull;
        const auto s = H - std::bit_width(_i);
        return 1ull << (s + (_i < (N >> s)));
    }

    // collects the exact nodes representing the range [l, r), in order
    [[nodiscard]] auto collect(size_t l, size_t r,
                               const bool reverse = false) const
        -> std::vector<size_t> {
        std::vector<size_t> nodes_l, nodes_r;
        for (l += N, r += N; l < r; l >>= 1, r >>= 1) {
            if (l & 1)
                nodes_l.push_back(l++);
            if (r & 1)
                nodes_r.push_back(--r);
        }
        if (reverse)
            std::swap(nodes_l, nodes_r);
        nodes_l.reserve(nodes_l.size() + nodes_r.size());
        std::ranges::copy(nodes_r | std::views::reverse,
                          std::back_inserter(nodes_l));
        return nodes_l;
    }

    // recomputes nodes on path from i to root
    void pull(size_t _i) {
        while (_i >>= 1) {
            data[_i] = Func(data[2 * _i], data[2 * _i + 1]);
        }
    }

    void set(const size_t i, const T val) {
        data[i + N] = val;
        pull(i + N);
    }

    auto query(const size_t l, const size_t r) -> T {
        return std::ranges::fold_left(
            collect(l, r) | std::views::transform([this](const auto i) -> auto {
                return data[i];
            }),
            Default, Func);
    }
};
