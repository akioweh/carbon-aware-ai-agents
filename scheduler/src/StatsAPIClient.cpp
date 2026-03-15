#include "StatsAPIClient.hpp"
#include "structs/Datacenter.hpp"
#include "utils/Coro.hpp"
#include "utils/Utils.hpp"
#include <algorithm>
#include <drogon/HttpClient.h>
#include <drogon/HttpRequest.h>
#include <drogon/HttpResponse.h>
#include <drogon/HttpTypes.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>
#include <map>
#include <optional>
#include <trantor/utils/Logger.h>

namespace scheduler {

using namespace std;
using namespace drogon;

StatsAPIClient::StatsAPIClient(string host) : host(std::move(host)) {}

auto StatsAPIClient::getLocations() -> Task<vector<Location>> {
    auto jsonPtr = co_await utils::makeGetRequest(host, getLocationsPath());

    const auto &json = *jsonPtr;
    auto locations = vector<Location>{};
    locations.reserve(json.size());
    for (const auto &item : json)
        locations.emplace_back(item["id"].asString(), item["name"].asString());
    co_return locations;
}

auto StatsAPIClient::getLoadForecast(const string &location)
    -> Task<std::optional<LoadTimeSeries>> {
    auto jsonPtr = co_await utils::makeGetRequest(host, getLoadPath(location));
    assert(jsonPtr);
    const auto &json = *jsonPtr;

    if (!json.isMember("location_id") || !json["location_id"].isString()) {
        LOG_WARN << "Response missing 'location_id' for location " << location
                 << ", defaulting to request parameter";
    }
    if (!json.isMember("data") || !json["data"].isArray()) {
        LOG_WARN << "Response missing 'data' array for location " << location
                 << ", returning empty time series";
        co_return LoadTimeSeries{.locationId = location,
                                 .metric = "TO REMOVE",
                                 .unit = "TO REMOVE",
                                 .data = {}};
    }

    auto data = decltype(LoadTimeSeries::data){};
    data.reserve(json["data"].size());
    for (const auto &item : json["data"]) {
        const auto tsOpt = utils::parseIso8601(item["timestamp"].asString());
        if (!tsOpt) {
            LOG_WARN << "Failed to parse timestamp, dropping data point: "
                     << item["timestamp"].asString();
            continue;
        }
        data.emplace_back(tsOpt.value(), item["value"].asDouble(),
                          item["is_forecast"].asBool(),
                          item["capacity"].asDouble());
    }

    co_return LoadTimeSeries{.locationId =
                                 json.get("location_id", location).asString(),
                             .metric = "TO REMOVE",
                             .unit = "TO REMOVE",
                             .data = std::move(data)};
}

auto StatsAPIClient::getCarbonIntensityForecast(const string &location)
    -> Task<std::optional<CarbonIntensityTimeSeries>> {
    auto jsonPtr =
        co_await utils::makeGetRequest(host, getCarbonIntensityPath(location));
    assert(jsonPtr);
    const auto &json = *jsonPtr;

    if (!json.isMember("location_id") || !json["location_id"].isString()) {
        LOG_WARN << "Response missing 'location_id' for location " << location
                 << ", defaulting to request parameter";
    }
    if (!json.isMember("data") || !json["data"].isArray()) {
        LOG_WARN << "Response missing 'data' array for location " << location
                 << ", returning empty time series";
        co_return CarbonIntensityTimeSeries{
            .locationId = json.get("location_id", location).asString(),
            .metric = "TO REMOVE",
            .unit = "TO REMOVE",
            .data = {}};
    }

    auto data = decltype(CarbonIntensityTimeSeries::data){};
    data.reserve(json["data"].size());
    for (const auto &item : json["data"]) {
        const auto tsOpt = utils::parseIso8601(item["timestamp"].asString());
        if (!tsOpt) {
            LOG_ERROR << "Failed to parse timestamp, dropping data point: "
                      << item["timestamp"].asString();
            continue;
        }
        data.emplace_back(tsOpt.value(), item["value"].asDouble(),
                          item["is_forecast"].asBool());
    }

    co_return CarbonIntensityTimeSeries{
        .locationId = json.get("location_id", location).asString(),
        .metric = "TO REMOVE",
        .unit = "TO REMOVE",
        .data = std::move(data)};
}

auto StatsAPIClient::getDatacenter(const string &datacenterName)
    -> Task<Datacenter> {
    auto [loadOpt, carbon_intensityOpt] =
        co_await coro::when_all(getLoadForecast(datacenterName),
                                getCarbonIntensityForecast(datacenterName));
    if (!loadOpt || !carbon_intensityOpt) {
        LOG_ERROR << "Failed to get complete data for " << datacenterName;
        co_return Datacenter{};
    }

    const auto &load = *loadOpt;
    const auto &carbon_intensity = *carbon_intensityOpt;
    // TODO: do we really want a map here?
    map<chrono::system_clock::time_point, double> ci_map;
    for (const auto &point : carbon_intensity.data)
        ci_map.emplace(point.timestamp, point.value);

    auto timeSeries = decltype(Datacenter::timeSeries){};
    timeSeries.reserve(load.data.size());

    for (const auto &point : load.data) {
        if (ci_map.contains(point.timestamp)) {
            timeSeries.emplace_back(point.timestamp, point.value,
                                    ci_map.at(point.timestamp),
                                    point.availableGpus);
        }
    }

    ranges::sort(timeSeries);

    co_return Datacenter{
        .id = load.locationId,
        .name = datacenterName,
        .hardwareSpec = {}, // TODO:
        .timeSeries = std::move(timeSeries),
    };
}

auto StatsAPIClient::getAllDatacenters() -> Task<vector<Datacenter>> {
    auto locations = co_await getLocations();
    if (locations.empty()) {
        LOG_ERROR << "No locations found";
        co_return {};
    }

    co_return co_await coro::when_all(
        locations | views::transform([this](const auto &loc) -> auto {
            return getDatacenter(loc.id);
        }) |
        ranges::to<vector>());
}

} // namespace scheduler
