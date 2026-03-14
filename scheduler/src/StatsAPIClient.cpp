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
    for (const auto &item : json) {
        locations.emplace_back(item["id"].asString(), item["name"].asString());
    }
    co_return locations;
}

auto StatsAPIClient::getLoadForecast(const string &location)
    -> Task<std::optional<LoadForecast>> {
    auto jsonPtr = co_await utils::makeGetRequest(host, getLoadPath(location));

    const auto &json = *jsonPtr;
    Capacity capacity{};
    if (json.isMember("capacity")) {
        capacity =
            Capacity{.maxLoad = json["capacity"]["max_load"].asDouble(),
                     .totalGpus = json["capacity"]["total_gpus"].asInt()};
    } else {
        LOG_WARN << "Capacity not found for " << location;
        capacity = Capacity{.maxLoad = 50., .totalGpus = 100};
    }

    auto data = decltype(LoadForecast::data){};
    if (json.isMember("data") && json["data"].isArray()) {
        data.reserve(json["data"].size());
        for (const auto &item : json["data"]) {
            const auto tsOpt =
                utils::parseIso8601(item["timestamp"].asString());
            if (tsOpt) {
                data.emplace_back(tsOpt.value(), item["value"].asDouble(),
                                  item["is_forecast"].asBool(),
                                  item.get("available_gpus", 0).asInt());
            } else {
                LOG_ERROR << "Failed to parse timestamp: "
                          << item["timestamp"].asString();
            }
        }
    }

    co_return LoadForecast{.locationId =
                               json.get("location_id", location).asString(),
                           .metric = json.get("metric", "").asString(),
                           .unit = json.get("unit", "").asString(),
                           .capacity = capacity,
                           .data = std::move(data)};
}

auto StatsAPIClient::getCarbonIntensityForecast(const string &location)
    -> Task<std::optional<CarbonIntensityForecast>> {
    auto jsonPtr =
        co_await utils::makeGetRequest(host, getCarbonIntensityPath(location));

    const auto &json = *jsonPtr;
    auto data = decltype(CarbonIntensityForecast::data){};
    if (json.isMember("data") && json["data"].isArray()) {
        data.reserve(json["data"].size());
        for (const auto &item : json["data"]) {
            const auto tsOpt =
                utils::parseIso8601(item["timestamp"].asString());
            if (tsOpt) {
                data.emplace_back(tsOpt.value(), item["value"].asDouble(),
                                  item["is_forecast"].asBool());
            } else {
                LOG_ERROR << "Failed to parse timestamp: "
                          << item["timestamp"].asString();
            }
        }
    }
    co_return CarbonIntensityForecast{
        .locationId = json.get("location_id", location).asString(),
        .metric = json.get("metric", "").asString(),
        .unit = json.get("unit", "").asString(),
        .data = std::move(data)};
}

auto StatsAPIClient::getDatacenter(const string &datacenterName)
    -> Task<Datacenter> {
    auto [loadOpt, sciOpt] =
        co_await coro::when_all(getLoadForecast(datacenterName),
                                getCarbonIntensityForecast(datacenterName));
    if (!loadOpt || !sciOpt) {
        LOG_ERROR << "Failed to get complete data for " << datacenterName;
        co_return Datacenter{};
    }

    const auto &load = *loadOpt;
    const auto &sci = *sciOpt;
    // TODO: do we really want a map here?
    map<chrono::system_clock::time_point, double> sciMap;
    for (const auto &point : sci.data)
        sciMap.emplace(point.timestamp, point.value);

    auto timeSeries = decltype(Datacenter::timeSeries){};
    timeSeries.reserve(load.data.size());

    for (const auto &point : load.data) {
        if (sciMap.contains(point.timestamp)) {
            timeSeries.emplace_back(point.timestamp, point.value,
                                    sciMap.at(point.timestamp),
                                    point.availableGpus);
        }
    }

    ranges::sort(timeSeries);

    co_return Datacenter{.id = load.locationId,
                         .name = datacenterName,
                         .maxLoad = load.capacity.maxLoad,
                         .totalGpus = load.capacity.totalGpus,
                         .timeSeries = std::move(timeSeries)};
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
