#ifndef SCHEDULER_STATS_API_CLIENT_HPP
#define SCHEDULER_STATS_API_CLIENT_HPP
#include "structs/TimeIntervalParams.hpp"
#pragma once

#include "structs/Datacenter.hpp"
#include <chrono>
#include <cstdlib>
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
    double capacity; // FLO (for this 5 min interval)
    // TODO: optimize struct padding alignment
    bool isForecast;
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
  public:
    static constexpr auto DEFAULT_STATS_API_HOST = "http://140.238.79.139:5000";

  private:
    std::string host;
    std::chrono::system_clock::time_point start_time;
    std::chrono::system_clock::time_point end_time;

    static auto getDefaultHost() -> const std::string & {
        static const auto res = []() -> std::string {
            const auto *env = std::getenv("STATS_API_HOST");
            return env ? std::string(env) : std::string(DEFAULT_STATS_API_HOST);
        }();
        return res;
    }
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
    StatsAPIClient();
    explicit StatsAPIClient(TimeIntervalParams time_interval,
                            std::string host = DEFAULT_STATS_API_HOST);

    [[nodiscard]] auto getLocations() const
        -> drogon::Task<std::vector<Location>>;
    // TODO: why do the following two return optional?
    // TODO: rename: these don't _only_ get forecasts (but also historical?)
    [[nodiscard]] auto getLoadForecast(const std::string &location) const
        -> drogon::Task<std::optional<LoadTimeSeries>>;
    [[nodiscard]] auto
    getCarbonIntensityForecast(const std::string &location) const
        -> drogon::Task<std::optional<CarbonIntensityTimeSeries>>;

    [[nodiscard]] auto getDatacenter(const std::string &datacenterName) const
        -> drogon::Task<Datacenter>;
    [[nodiscard]] auto getAllDatacenters() const
        -> drogon::Task<std::vector<Datacenter>>;
};

} // namespace scheduler

#endif // SCHEDULER_STATS_API_CLIENT_HPP
