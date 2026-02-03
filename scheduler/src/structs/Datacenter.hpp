#ifndef DATACENTER_HPP
#define DATACENTER_HPP
#pragma once

#include <chrono>
#include <string>
#include <vector>

/**
 * @class TimeSlot
 * @brief used in \ref Datacenter
 *
 */
struct TimeSlot {
    std::chrono::system_clock::time_point timestamp;
    double predictedLoad;
    double predictedGreenness;
    int availableGpus;
};

// defined as a free function for TimeSlot to remain an aggregate type
inline auto operator<=>(const TimeSlot &lhs, const TimeSlot &rhs) {
    return lhs.timestamp <=> rhs.timestamp;
};
// defined as a free function for TimeSlot to remain an aggregate type
inline auto operator==(const TimeSlot &lhs, const TimeSlot &rhs) {
    return lhs.timestamp == rhs.timestamp &&
           lhs.predictedLoad == rhs.predictedLoad &&
           lhs.predictedGreenness == rhs.predictedGreenness &&
           lhs.availableGpus == rhs.availableGpus;
}

/**
 * @class Datacenter
 * @brief DTO for per-location information as per stats API definition.
 */
struct Datacenter {
    std::string id;
    std::string name;
    double maxLoad;
    int totalGpus;
    std::vector<TimeSlot> timeSeries;
};

#endif // DATACENTER_HPP
