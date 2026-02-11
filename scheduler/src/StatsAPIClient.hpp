#ifndef STATS_API_CLIENT
#define STATS_API_CLIENT
#pragma once

#include <chrono>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>
#include <optional>
#include <string>
#include <structs/Datacenter.hpp>
#include <vector>

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

struct GreennessForecastDataPoint {
    std::chrono::system_clock::time_point timestamp;
    double value;
    bool isForecast;
};

struct GreennessForecast {
    std::string locationId;
    std::string metric;
    std::string unit;
    std::vector<GreennessForecastDataPoint> data;
};

class StatsAPIClient {
  private:
    std::string host;

    static auto getLoadPath(const std::string &locationId) -> std::string {
        return "/locations/" + locationId + "/metrics/forecast_load";
    }
    static auto getGreennessPath(const std::string &locationId) -> std::string {
        return "/locations/" + locationId + "/metrics/forecast_greenness";
    }
    static auto getLocationsPath() -> std::string { return "/locations"; }

  public:
    explicit StatsAPIClient(std::string host = "http://127.0.0.1:5000");

    auto getLocations() -> drogon::Task<std::vector<Location>>;
    auto getLoadForecast(const std::string &locationId)
        -> drogon::Task<std::optional<LoadForecast>>;
    auto getGreennessForecast(const std::string &locationId)
        -> drogon::Task<std::optional<GreennessForecast>>;

    auto getDatacenter(const std::string &locationId)
        -> drogon::Task<Datacenter>;
    auto getAllDatacenters() -> drogon::Task<std::vector<Datacenter>>;
};

#endif // STATS_API_CLIENT
