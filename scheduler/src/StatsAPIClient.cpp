#include "StatsAPIClient.hpp"
#include "structs/Datacenter.hpp"
#include "structs/TimeIntervalParams.hpp"
#include "utils/Coro.hpp"
#include "utils/TimeGridder.hpp"
#include "utils/Utils.hpp"
#include <algorithm>
#include <drogon/HttpClient.h>
#include <drogon/HttpRequest.h>
#include <drogon/HttpResponse.h>
#include <drogon/HttpTypes.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>
#include <optional>
#include <trantor/utils/Logger.h>

namespace scheduler {

using namespace std;
using namespace drogon;

StatsAPIClient::StatsAPIClient() : host(getDefaultHost()) {}
StatsAPIClient::StatsAPIClient(TimeIntervalParams time_interval, string host)
    : host(std::move(host)), time_interval(time_interval) {}

auto StatsAPIClient::addTimeIntervalPathParams() const -> std::string {
    std::string params = "?";
    if (time_interval.start)
        params +=
            "start_time=" + utils::toIso8601(time_interval.start.value()) + '&';
    if (time_interval.end)
        params += "end_time=" + utils::toIso8601(time_interval.end.value());

    if (params.back() == '?' || params.back() == '&')
        params.pop_back();
    return params;
}

auto StatsAPIClient::getLocations() const -> Task<vector<Location>> {
    auto jsonPtr = co_await utils::makeGetRequest(host, getLocationsPath());

    const auto &json = *jsonPtr;
    auto locations = vector<Location>{};
    locations.reserve(json.size());
    for (const auto &item : json)
        locations.emplace_back(item["id"].asString(), item["name"].asString());
    co_return locations;
}

auto StatsAPIClient::getLoadForecast(const string &location) const
    -> Task<optional<LoadTimeSeries>> {
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
        co_return LoadTimeSeries{.locationId = location, .data = {}};
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
                          item["capacity"].asDouble(),
                          item["is_forecast"].asBool());
    }

    co_return LoadTimeSeries{.locationId =
                                 json.get("location_id", location).asString(),
                             .data = std::move(data)};
}

auto StatsAPIClient::getCarbonIntensityForecast(const string &location) const
    -> Task<optional<CarbonIntensityTimeSeries>> {
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
        .data = std::move(data)};
}

auto StatsAPIClient::getDatacenter(const string &datacenterName) const
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

    if (load.data.empty() || carbon_intensity.data.empty()) {
        LOG_WARN << "Empty data arrays returned for " << datacenterName;
        co_return Datacenter{
            .id = load.locationId,
            .name = datacenterName,
            .timeSeries = {},
        };
    }

    // detect start and end times
    const auto tps1 = load.data | views::transform(&LoadDataPoint::timestamp);
    const auto tps2 = carbon_intensity.data |
                      views::transform(&CarbonIntensityDataPoint::timestamp);
    auto start = min(ranges::min(tps1), ranges::min(tps2));
    auto end = max(ranges::max(tps1), ranges::max(tps2));

    // use time gridder to align data points by timestamp and
    // transform into a sorted time series. missing data is defaulted to 0
    // as a side effect, this "aligns" all timestamps to whole-5-min marks
    const auto index_offset = TIME_GRIDDER.toIndex(start);
    const auto n = TIME_GRIDDER.toIndex(end) - index_offset + 1;
    auto timeSeries = decltype(Datacenter::timeSeries)(n);
    for (const auto idx : views::iota(int64_t{}, n))
        timeSeries[idx].timestamp =
            TIME_GRIDDER.toTimePoint(idx + index_offset);
    // assume no multiple data points within an interval; overwrite
    for (const auto &pt : load.data) {
        const auto idx = TIME_GRIDDER.toIndex(pt.timestamp) - index_offset;
        timeSeries[idx].load = pt.value;
        timeSeries[idx].capacity = pt.capacity;
        // isForecast is ignored
    }
    for (const auto &pt : carbon_intensity.data) {
        const auto idx = TIME_GRIDDER.toIndex(pt.timestamp) - index_offset;
        timeSeries[idx].carbon_intensity = pt.value;
    }

    co_return Datacenter{
        .id = load.locationId,
        .name = datacenterName,
        .timeSeries = std::move(timeSeries),
    };
}

auto StatsAPIClient::getAllDatacenters() const -> Task<vector<Datacenter>> {
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
