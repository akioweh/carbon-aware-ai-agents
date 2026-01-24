#ifndef STATS_API_CLIENT
#define STATS_API_CLIENT
#pragma once

#include "Datacenter.hpp"
#include <chrono>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>
#include <optional>
#include <string>
#include <vector>

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

    static auto getLoadPath(const std::string &datacenterName) -> std::string {
        return "/locations/" + datacenterName + "/metrics/forecast_load";
    }
    static auto getGreennessPath(const std::string &datacenterName)
        -> std::string {
        return "/locations/" + datacenterName + "/metrics/forecast_greenness";
    }
    static auto getDatacenterPath() -> std::string { return "/datacenter"; }

  public:
    explicit StatsAPIClient(std::string host = "http://127.0.0.1:5000");

    auto getDatacenterNames() -> drogon::Task<std::vector<std::string>>;
    auto getLoadForecast(const std::string &location)
        -> drogon::Task<std::optional<LoadForecast>>;
    auto getGreennessForecast(const std::string &location)
        -> drogon::Task<std::optional<GreennessForecast>>;

    auto getDatacenter(const std::string &datacenterName)
        -> drogon::Task<Datacenter>;
    auto getAllDatacenters() -> drogon::Task<std::vector<Datacenter>>;
};

#endif // STATS_API_CLIENT
