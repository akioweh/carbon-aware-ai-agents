#ifndef SCHEDULER_UTILS_TIMEGRINDER_HPP
#define SCHEDULER_UTILS_TIMEGRINDER_HPP
#pragma once

#include <chrono>

namespace scheduler::utils {

using SysNanoseconds = std::chrono::sys_time<std::chrono::nanoseconds>;

inline constexpr SysNanoseconds MIN_TIME =
    std::chrono::sys_days{std::chrono::January / 1 / 1970};

inline constexpr SysNanoseconds MAX_TIME =
    std::chrono::sys_days{std::chrono::January / 1 / 2100};

template <typename T> struct is_duration : std::false_type {};

template <typename Rep, typename Period>
struct is_duration<std::chrono::duration<Rep, Period>> : std::true_type {};

template <typename T>
concept Duration = is_duration<T>::value;

template <typename T>
concept Clock = std::chrono::is_clock_v<T>;

template <Duration Resolution, Clock clock_t = std::chrono::system_clock>
class TimeGridder {
  public:
    using time_point_t = std::chrono::time_point<clock_t>;
    using duration_t = time_point_t::duration; // nanoseconds if system_clock

    constexpr explicit TimeGridder(const time_point_t &start = {})
        : start_(start) {}

    // rounds down
    [[nodiscard]] constexpr auto toIndex(const time_point_t &tp) const
        -> long long {
        return std::chrono::floor<Resolution>(tp - start_).count();
    }

    // rounds up
    [[nodiscard]] constexpr auto toIndexCeil(const time_point_t &tp) const
        -> long long {
        return std::chrono::ceil<Resolution>(tp - start_).count();
    }

    [[nodiscard]] constexpr auto toTimePoint(const long long index) const
        -> time_point_t {
        return start_ + Resolution{index};
    }

    friend constexpr auto operator==(const TimeGridder &lhs,
                                     const TimeGridder &rhs) noexcept -> bool {
        return lhs.start_ == rhs.start_;
    }

  private:
    time_point_t start_;
};
} // namespace scheduler::utils

#endif // SCHEDULER_JOB_IDENTIFIER_HPP
