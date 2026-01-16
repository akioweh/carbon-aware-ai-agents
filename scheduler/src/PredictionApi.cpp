#include <DatacenterSpecificInformation.hpp>
#include <PredictedDatacenterInformation.hpp>
#include <PredictionApi.hpp>
#include <algorithm>
#include <drogon/HttpClient.h>
#include <drogon/HttpRequest.h>
#include <drogon/HttpResponse.h>
#include <drogon/HttpTypes.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>
#include <trantor/utils/Logger.h>
#include <utils/Utils.hpp>

using namespace std;
using namespace drogon;

auto PredictionApi::getLoadPath(const string &datacenterName) -> string {
    return "/locations/" + datacenterName + "/metrics/forecast_load";
}

auto PredictionApi::getGreennessPath(const string &datacenterName) -> string {
    return "/locations/" + datacenterName + "/metrics/forecast_greenness";
}

auto PredictionApi::getDataSingleDatacenter(const string &datacenterName)
    -> Task<vector<PredictedDatacenterInformation>> {
    const string loadPath = getLoadPath(datacenterName);
    const string greenneesPath = getGreennessPath(datacenterName);

    auto loadJsonPromise = scheduler::utils::makeGetRequest(host, loadPath);
    auto greenneesJsonPromise = scheduler::utils::makeGetRequest(host, greenneesPath);

    // auto [loadJsonPtr, greenneesJsonPtr] = co_await when_all(loadJsonPromise,
    // greenneesJsonPromise) ; later I will write my own when_all to make this
    // sexy pretty

    auto [loadJsonPtr, greenneesJsonPtr] =
        tuple{co_await loadJsonPromise, co_await greenneesJsonPromise};

    if (!loadJsonPtr || !greenneesJsonPtr) {
        LOG_ERROR << "Failed to get data from stats API";
        co_return {};
    }

    auto loadData = parseJsonForLoad(*loadJsonPtr);
    auto greennessData = parseJsonForGreenness(*greenneesJsonPtr);
    auto datacenterSpecificInfo =
        DatacenterSpecificInformation::parseJsonForDCSpecificInfo(
            datacenterName, *loadJsonPtr);

    std::ranges::sort(loadData);
    std::ranges::sort(greennessData);
    // sorting after timestamps

    co_return constructDCPredictions(loadData, greennessData,
                                     datacenterSpecificInfo);
}

auto PredictionApi::constructDCPredictions(
    std::vector<std::pair<long long, double>> &loadData,
    std::vector<std::pair<long long, double>> &greennessData,
    DatacenterSpecificInformation &datacenterSpecificInfo)
    -> std::vector<PredictedDatacenterInformation> {

    if (loadData.size() == 0)
        return {};
    // if we dont have any data we cannot deduce the length of interval

    long long lengthOfInterval = loadData[1].first - loadData[0].first;

    vector<PredictedDatacenterInformation> DCInfo;

    for (unsigned long long i = 0;
         i < min(greennessData.size(), loadData.size()); i++) {
        auto [timestamp, predictedLoad] = loadData[i];
        auto [dummy, predictedGreeness] = greennessData[i];
        DCInfo.emplace_back(timestamp, lengthOfInterval, predictedLoad,
                            predictedGreeness, datacenterSpecificInfo);
    }

    return DCInfo;
}

auto PredictionApi::getData()
    -> Task<map<long long, vector<PredictedDatacenterInformation>>> {
    vector<string> datacenterNamesList = {"Data-Center-1", "Data-Center-2",
                                          "Data-Center-3", "Data-Center-4",
                                          "Data-Center-5"};
    // this will be made an API call to get the names. It just isnt implemented
    // yet.

    vector<Task<vector<PredictedDatacenterInformation>>> promisedData;
    promisedData.reserve(datacenterNamesList.size());
    for (auto &name : datacenterNamesList)
        promisedData.push_back(getDataSingleDatacenter(name));

    map<long long, vector<PredictedDatacenterInformation>> data;
    for (auto &tasks : promisedData) {
        auto dcData = co_await tasks;
        if (dcData.empty())
            continue;
        data[dcData.front().datacenterInfo.datacenterId] = dcData;
    }
    co_return data;
}

auto PredictionApi::parseJsonForLoad(const Json::Value &respJson)
    -> vector<pair<long long, double>> {
    vector<pair<long long, double>> loadData;
    for (auto obj : respJson["data"]) {
        long long timestamp =
            scheduler::utils::parseTimestampSeconds(obj["timestamp"].asString());
        double load = obj["value"].asDouble();
        loadData.emplace_back(timestamp, load);
    }
    return loadData;
}

auto PredictionApi::parseJsonForGreenness(const Json::Value &respJson)
    -> vector<pair<long long, double>> {
    vector<pair<long long, double>> greenessData;
    for (auto obj : respJson["data"]) {
        long long timestamp =
            scheduler::utils::parseTimestampSeconds(obj["timestamp"].asString());
        double load = obj["value"].asDouble();
        greenessData.emplace_back(timestamp, load);
    }
    return greenessData;
}
