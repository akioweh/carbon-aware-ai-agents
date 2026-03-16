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
 * @brief used in \ref Datacenter, represents a 5-min interval
 *
 */
struct TimeSlot {
    std::chrono::system_clock::time_point timestamp;
    double load{};             // Floating-Point Operations (FLO) load
    double carbon_intensity{}; // gCO2eq/kWh
    double capacity{};         // FLO capacity for this 5 min interval
};

// defined as a free function for TimeSlot to remain an aggregate type
inline auto operator<=>(const TimeSlot &lhs, const TimeSlot &rhs) {
    return lhs.timestamp <=> rhs.timestamp;
};
// defined as a free function for TimeSlot to remain an aggregate type
inline auto operator==(const TimeSlot &lhs, const TimeSlot &rhs) {
    return lhs.timestamp == rhs.timestamp && lhs.load == rhs.load &&
           lhs.carbon_intensity == rhs.carbon_intensity &&
           lhs.capacity == rhs.capacity;
}

inline auto f_toJson(const TimeSlot &obj) -> Json::Value {
    auto res = Json::Value{};
    res["timestamp"] = utils::toIso8601(obj.timestamp);
    res["carbon_intensity"] = obj.carbon_intensity;
    res["load"] = obj.load;
    res["capacity"] = obj.capacity;
    return res;
}

/**
 * @class Datacenter
 * @brief Internal aggregator of datacenter-specific info needed for scheduling.
 *
 * Constructed by StatsAPIClient from multiple deserialized API responses.
 * Also happens to be retunred by the forecast forwarding endpoint.
 */
struct Datacenter {
    std::string id;
    std::string name;
    std::vector<TimeSlot> timeSeries;
};

inline auto f_toJson(const Datacenter &obj) -> Json::Value {
    auto res = Json::Value{};
    res["location"] = obj.id;
    res["timeseries"] = Json::Value(Json::arrayValue);
    for (const auto &block : obj.timeSeries)
        res["timeseries"].append(toJson(block));
    return res;
}

} // namespace scheduler

#endif // SCHEDULER_DATACENTER_HPP
