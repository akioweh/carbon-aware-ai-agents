#include "StatsAPIClient.hpp"
#include <Datacenter.hpp>
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
#include <utils/Coro.hpp>
#include <utils/Utils.hpp>

using namespace std;
using namespace drogon;

StatsAPIClient::StatsAPIClient(string host) : host(std::move(host)) {}

auto StatsAPIClient::getDatacenterNames() -> Task<vector<string>> {
    auto jsonPtr =
        co_await scheduler::utils::makeGetRequest(host, getDatacenterPath());
    if (!jsonPtr) {
        LOG_ERROR << "Failed to get datacenter names";
        co_return {};
    }

    const auto &json = *jsonPtr;
    auto names = vector<string>(json.size());
    for (const auto &&[i, name] : ranges::views::enumerate(json))
        names[i] = name.asString();
    co_return names;
}

auto StatsAPIClient::getLoadForecast(const string &location)
    -> Task<std::optional<LoadForecast>> {
    auto jsonPtr =
        co_await scheduler::utils::makeGetRequest(host, getLoadPath(location));
    if (!jsonPtr) {
        LOG_ERROR << "Failed to get load forecast for " << location;
        co_return std::nullopt;
    }

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
                scheduler::utils::parseIso8601(item["timestamp"].asString());
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

auto StatsAPIClient::getGreennessForecast(const string &location)
    -> Task<std::optional<GreennessForecast>> {
    auto jsonPtr = co_await scheduler::utils::makeGetRequest(
        host, getGreennessPath(location));
    if (!jsonPtr) {
        LOG_ERROR << "Failed to get greenness forecast for " << location;
        co_return std::nullopt;
    }

    const auto &json = *jsonPtr;
    auto data = decltype(GreennessForecast::data){};
    if (json.isMember("data") && json["data"].isArray()) {
        data.reserve(json["data"].size());
        for (const auto &item : json["data"]) {
            const auto tsOpt =
                scheduler::utils::parseIso8601(item["timestamp"].asString());
            if (tsOpt) {
                data.emplace_back(tsOpt.value(), item["value"].asDouble(),
                                  item["is_forecast"].asBool());
            } else {
                LOG_ERROR << "Failed to parse timestamp: "
                          << item["timestamp"].asString();
            }
        }
    }
    co_return GreennessForecast{
        .locationId = json.get("location_id", location).asString(),
        .metric = json.get("metric", "").asString(),
        .unit = json.get("unit", "").asString(),
        .data = std::move(data)};
}

auto StatsAPIClient::getDatacenter(const string &datacenterName)
    -> Task<Datacenter> {
    auto [loadOpt, greennessOpt] = co_await scheduler::coro::when_all(
        getLoadForecast(datacenterName), getGreennessForecast(datacenterName));
    if (!loadOpt || !greennessOpt) {
        LOG_ERROR << "Failed to get complete data for " << datacenterName;
        co_return Datacenter{};
    }

    const auto &load = *loadOpt;
    const auto &greenness = *greennessOpt;
    // TODO: do we really want a map here?
    map<chrono::system_clock::time_point, double> greennessMap;
    for (const auto &point : greenness.data)
        greennessMap.emplace(point.timestamp, point.value);

    auto timeSeries = decltype(Datacenter::timeSeries){};
    timeSeries.reserve(load.data.size());

    for (const auto &point : load.data) {
        if (greennessMap.contains(point.timestamp)) {
            timeSeries.emplace_back(point.timestamp, point.value,
                                    greennessMap.at(point.timestamp),
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
    auto names = co_await getDatacenterNames();
    if (names.empty()) {
        LOG_ERROR << "No datacenters found";
        co_return {};
    }

    co_return co_await scheduler::coro::when_all(
        names | views::transform([this](const auto &name) -> auto {
            return getDatacenter(name);
        }) |
        ranges::to<vector>());
}
