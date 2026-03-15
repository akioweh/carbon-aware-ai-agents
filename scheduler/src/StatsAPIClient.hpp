#ifndef SCHEDULER_STATS_API_CLIENT_HPP
#define SCHEDULER_STATS_API_CLIENT_HPP
#pragma once

#include "structs/Datacenter.hpp"
#include <chrono>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>
#include <optional>
#include <string>
#include <vector>

namespace scheduler {

/// Location as returned by /locations endpoint
struct Location {
    std::string id;
    std::string name;
};

struct LoadForecastDataPoint {
    std::chrono::system_clock::time_point timestamp;
    double value;
    bool isForecast;
    int availableGpus;
};

struct Capacity {
    double maxLoad;
    int totalGpus;
};

struct LoadForecast {
    std::string locationId;
    std::string metric;
    std::string unit;
    Capacity capacity;
    std::vector<LoadForecastDataPoint> data;
};

struct CarbonIntensityForecastDataPoint {
    std::chrono::system_clock::time_point timestamp;
    double value;
    bool isForecast;
};

struct CarbonIntensityForecast {
    std::string locationId;
    std::string metric;
    std::string unit;
    std::vector<CarbonIntensityForecastDataPoint> data;
};

class StatsAPIClient {
  private:
    std::string host;

    static auto getLoadPath(const std::string &locationId) -> std::string {
        return "/locations/" + locationId + "/metrics/forecast_load";
    }
    static auto getCarbonIntensityPath(const std::string &locationId)
        -> std::string {
        return "/locations/" + locationId +
               "/metrics/forecast_carbon_intensity";
    }
    static auto getLocationsPath() -> std::string { return "/locations"; }

  public:
    explicit StatsAPIClient(std::string host = "http://140.238.79.139:5000");

    auto getLocations() -> drogon::Task<std::vector<Location>>;
    auto getLoadForecast(const std::string &location)
        -> drogon::Task<std::optional<LoadForecast>>;
    auto getCarbonIntensityForecast(const std::string &location)
        -> drogon::Task<std::optional<CarbonIntensityForecast>>;

    auto getDatacenter(const std::string &datacenterName)
        -> drogon::Task<Datacenter>;
    auto getAllDatacenters() -> drogon::Task<std::vector<Datacenter>>;
};

} // namespace scheduler

#endif // SCHEDULER_STATS_API_CLIENT_HPP
