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

/**
 * @class Location
 * @brief DTO from GET /locations
 *
 */
struct Location {
    std::string id;
    std::string name;
};

struct LoadDataPoint {
    std::chrono::system_clock::time_point timestamp;
    double value;
    // TODO: optimize struct padding alignment
    bool isForecast;
    double capacity; // FLO (for this 5 min interval)
};

/**
 * @class LoadTimeSeries
 * @brief DTO from GET /locations/{locationId}/metrics/forecast_load
 *
 * also happens to contain capacity info
 */
struct LoadTimeSeries {
    std::string locationId;
    std::vector<LoadDataPoint> data;
};

struct CarbonIntensityDataPoint {
    std::chrono::system_clock::time_point timestamp;
    double value;
    bool isForecast;
};

/**
 * @class CarbonIntensityTimeSeries
 * @brief DTO from GET /locations/{locationId}/metrics/forecast_carbon_intensity
 *
 */
struct CarbonIntensityTimeSeries {
    std::string locationId;
    std::vector<CarbonIntensityDataPoint> data;
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
    // TODO: why do the following two return optional?
    // TODO: rename: these don't _only_ get forecasts (but also historical?)
    auto getLoadForecast(const std::string &location)
        -> drogon::Task<std::optional<LoadTimeSeries>>;
    auto getCarbonIntensityForecast(const std::string &location)
        -> drogon::Task<std::optional<CarbonIntensityTimeSeries>>;

    auto getDatacenter(const std::string &datacenterName)
        -> drogon::Task<Datacenter>;
    auto getAllDatacenters() -> drogon::Task<std::vector<Datacenter>>;
};

} // namespace scheduler

#endif // SCHEDULER_STATS_API_CLIENT_HPP
