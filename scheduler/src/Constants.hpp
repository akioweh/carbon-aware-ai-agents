#ifndef SCHEDULER_CONSTANTS_HPP
#define SCHEDULER_CONSTANTS_HPP
#pragma once

#include <limits>

namespace scheduler::constants {

// algo
inline constexpr auto MIN_E_WORK = 0.001;
inline constexpr auto DEFAULT_RESOLUTION = 10000;
inline constexpr auto EPSILON = 1e-6;
inline constexpr auto INF = std::numeric_limits<double>::max() / 10;

// network
inline constexpr auto DEFAULT_TIMEOUT_SEC = 10.;

} // namespace scheduler::constants

#endif // SCHEDULER_CONSTANTS_HPP
