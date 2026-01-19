#ifndef SCHEDULED_INTERVAL
#define SCHEDULED_INTERVAL
#pragma once

#include <Serializable.hpp>
#include <chrono>
#include <string>
#include <utils/Utils.hpp>

class ScheduledInterval {
  public:
    std::chrono::system_clock::time_point timestamp;
    std::string jobId;
    std::string location;
    double additionalLoad; /// thats what we scheduled
    double totalLoad;      /// thats what we scheduled + predicted at that time

    ScheduledInterval(std::chrono::system_clock::time_point timestamp,
                      std::string jobId, std::string location,
                      double additionalLoad, double totalLoad)
        : timestamp(timestamp), jobId(std::move(jobId)),
          location(std::move(location)), additionalLoad(additionalLoad),
          totalLoad(totalLoad) {};

    auto operator<(const ScheduledInterval &other) const -> bool {
        return timestamp < other.timestamp;
    }

    void show() const {
        std::cout << scheduler::utils::toIso8601(timestamp) << " " << jobId
                  << " " << additionalLoad << " " << totalLoad << ",\n";
    }
};

inline auto f_toJson(const ScheduledInterval &obj) -> Json::Value {
    auto res = Json::Value{};
    res["timestamp"] = scheduler::utils::toIso8601(obj.timestamp);
    res["job_id"] = obj.jobId;
    res["additional_load"] = obj.additionalLoad;
    res["total_load"] = obj.totalLoad;
    res["location"] = obj.location;
    return res;
}

static_assert(Serializable<ScheduledInterval>);

#endif
