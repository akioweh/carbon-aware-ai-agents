#ifndef SCHEDULER_STATS_API_CLIENT_HPP
#define SCHEDULER_STATS_API_CLIENT_HPP
#pragma once

#include "structs/Datacenter.hpp"
#include "structs/TimeIntervalParams.hpp"
#include "utils/Utils.hpp"
#include <chrono>
#include <cstdlib>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>
#include <memory>
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

class StatsAPIClient;
// Singleton backdoor for tests
auto createFreeStatsAPIClient() -> std::shared_ptr<StatsAPIClient>;

/**
 * @class StatsAPIClient
 * @brief Singleton client for fetching data from the Stats API.
 *
 * TODO: implement caching (e-tag based? expiry?)
 */
class StatsAPIClient {
    friend auto createFreeStatsAPIClient() -> std::shared_ptr<StatsAPIClient>;

  public:
    // overridable via STATS_API_HOST environment variable
    static constexpr auto DEFAULT_STATS_API_HOST = "http://140.238.79.139:5000";

    [[nodiscard]] auto getLocations() const
        -> drogon::Task<std::vector<Location>>;

    // TODO: why do the following two return optional?
    // TODO: rename: these don't _only_ get forecasts (but also historical?)
    [[nodiscard]] auto getLoadForecast(
        const std::string &location,
        std::optional<TimeIntervalParams> interval = std::nullopt) const
        -> drogon::Task<std::optional<LoadTimeSeries>>;
    [[nodiscard]] auto getCarbonIntensityForecast(
        const std::string &location,
        std::optional<TimeIntervalParams> interval = std::nullopt) const
        -> drogon::Task<std::optional<CarbonIntensityTimeSeries>>;

    [[nodiscard]] auto getDatacenter(
        const std::string &datacenterName,
        std::optional<TimeIntervalParams> interval = std::nullopt) const
        -> drogon::Task<Datacenter>;
    [[nodiscard]] auto getAllDatacenters(
        std::optional<std::string> preferred_datacenter = {},
        std::optional<TimeIntervalParams> interval = std::nullopt) const
        -> drogon::Task<std::vector<Datacenter>>;

    StatsAPIClient(const StatsAPIClient &) = delete;
    StatsAPIClient(StatsAPIClient &&) = delete;
    auto operator=(const StatsAPIClient &) -> StatsAPIClient & = delete;
    auto operator=(StatsAPIClient &&) -> StatsAPIClient & = delete;

    static auto getInstance() -> StatsAPIClient & {
        static StatsAPIClient instance;
        return instance;
    }

    static auto getHost() -> const std::string & {
        static const auto res = []() -> std::string {
            const auto *env = std::getenv("STATS_API_HOST");
            return env ? std::string(env) : std::string(DEFAULT_STATS_API_HOST);
        }();
        return res;
    }

    const std::string host;

  private:
    static auto
    addTimeIntervalPathParams(std::optional<TimeIntervalParams> interval)
        -> std::string;

    static auto getLoadPath(const std::string &locationId,
                            const std::optional<TimeIntervalParams> &interval =
                                std::nullopt) -> std::string {
        return "/locations/" + locationId + "/metrics/forecast_load" +
               addTimeIntervalPathParams(interval);
    }
    static auto getCarbonIntensityPath(
        const std::string &locationId,
        const std::optional<TimeIntervalParams> &interval = std::nullopt)
        -> std::string {
        return "/locations/" + locationId +
               "/metrics/forecast_carbon_intensity" +
               addTimeIntervalPathParams(interval);
    }
    static auto getLocationsPath() -> std::string { return "/locations"; }

    StatsAPIClient();
};

} // namespace scheduler

#endif // SCHEDULER_STATS_API_CLIENT_HPP
