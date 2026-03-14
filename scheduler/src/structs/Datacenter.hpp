#ifndef SCHEDULER_DATACENTER_HPP
#define SCHEDULER_DATACENTER_HPP
#pragma once

#include "Serializable.hpp"
#include "utils/Utils.hpp"
#include <chrono>
#include <json/value.h>
#include <string>
#include <vector>

namespace scheduler {

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

inline auto f_toJson(const TimeSlot &obj) -> Json::Value {
    auto res = Json::Value{};
    res["timestamp"] = utils::toIso8601(obj.timestamp);
    res["greeness"] = obj.predictedGreenness;
    res["load"] = obj.predictedLoad;
    return res;
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

inline auto f_toJson(const Datacenter &obj) -> Json::Value {
    auto res = Json::Value{};
    res["location"] = obj.id;
    res["max_load"] = obj.maxLoad;
    res["timeseries"] = Json::Value(Json::arrayValue);
    for (const auto &block : obj.timeSeries) {
        res["timeseries"].append(toJson(block));
    }
    return res;
}

} // namespace scheduler

#endif // SCHEDULER_DATACENTER_HPP
