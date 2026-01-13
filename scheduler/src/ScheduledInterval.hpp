#ifndef SCHEDULED_INTERVAL
#define SCHEDULED_INTERVAL
#pragma once

#include <Serializable.hpp>
#include <chrono>
#include <string>
#include <utils/Utils.hpp>

class ScheduledInterval : public Serializable {
  public:
    std::chrono::system_clock::time_point timestamp;
    std::string jobId;
    double additionalLoad; /// thats what we scheduled
    double totalLoad;      /// thats what we scheduled + predicted at that time

    ScheduledInterval(std::chrono::system_clock::time_point timestamp,
                      std::string jobId, double additionalLoad,
                      double totalLoad)
        : timestamp(timestamp), jobId(std::move(jobId)),
          additionalLoad(additionalLoad), totalLoad(totalLoad) {};

    auto operator<(const ScheduledInterval &other) const -> bool {
        return timestamp < other.timestamp;
    }

    void show() const {
        std::cout << Utils::toIso8601(timestamp) << " " << jobId << " "
                  << additionalLoad << " " << totalLoad << ",\n";
    }

    [[nodiscard]] auto toJson() const -> Json::Value override {
        auto intervalJson = Json::Value{};
        intervalJson["timestamp"] = Utils::toIso8601(timestamp);
        intervalJson["job_id"] = jobId;
        intervalJson["additional_load"] = additionalLoad;
        intervalJson["total_load"] = totalLoad;
        return intervalJson;
    }
};

#endif
