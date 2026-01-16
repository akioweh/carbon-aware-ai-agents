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
#include <utils/Coro.hpp>
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
    const string greennessPath = getGreennessPath(datacenterName);

    auto loadJsonPromise = scheduler::utils::makeGetRequest(host, loadPath);
    auto greennessJsonPromise =
        scheduler::utils::makeGetRequest(host, greennessPath);

    vector<Task<shared_ptr<Json::Value>>> Promises;
    Promises.push_back(std::move(loadJsonPromise));
    Promises.push_back(std::move(greennessJsonPromise));
    // tasks are move only so i cannot do initilizer list

    auto requestPtrs = co_await scheduler::coro::when_all(std::move(Promises));
    auto [loadJsonPtr, greennessJsonPtr] =
        tuple{requestPtrs[0], requestPtrs[1]};

    if (!loadJsonPtr || !greennessJsonPtr) {
        LOG_ERROR << "Failed to get data from stats API";
        co_return {};
    }

    auto loadData = parseJsonForLoad(*loadJsonPtr);
    auto greennessData = parseJsonForGreenness(*greennessJsonPtr);
    auto datacenterSpecificInfo =
        DatacenterSpecificInformation::parseJsonForDCSpecificInfo(
            datacenterName, *loadJsonPtr);

    ranges::sort(loadData);
    ranges::sort(greennessData);
    // sorting after timestamps

    co_return constructDCPredictions(loadData, greennessData,
                                     datacenterSpecificInfo);
}

auto PredictionApi::constructDCPredictions(
    vector<pair<chrono::system_clock::time_point, double>> &loadData,
    vector<pair<chrono::system_clock::time_point, double>> &greennessData,
    DatacenterSpecificInformation &datacenterSpecificInfo)
    -> vector<PredictedDatacenterInformation> {

    if (loadData.size() == 0)
        return {};
    // if we dont have any data we cannot deduce the length of interval

    // assuming uniform intervals
    auto duration = loadData[1].first - loadData[0].first;
    auto lengthOfInterval = chrono::duration_cast<chrono::seconds>(duration);

    vector<PredictedDatacenterInformation> DCInfo;

    for (unsigned long long i = 0;
         i < min(greennessData.size(), loadData.size()); i++) {
        auto [timestamp, predictedLoad] = loadData[i];
        auto [dummy, predictedGreenness] = greennessData[i];
        DCInfo.emplace_back(timestamp, lengthOfInterval, predictedLoad,
                            predictedGreenness, datacenterSpecificInfo);
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

    auto resolvedData =
        co_await scheduler::coro::when_all(std::move(promisedData));

    map<long long, vector<PredictedDatacenterInformation>> data;
    for (auto &dcData : resolvedData) {
        if (dcData.empty())
            continue;
        data[dcData.front().datacenterInfo.datacenterId] = dcData;
    }
    co_return data;
}

auto PredictionApi::parseJsonForLoad(const Json::Value &respJson)
    -> vector<pair<chrono::system_clock::time_point, double>> {
    vector<pair<chrono::system_clock::time_point, double>> loadData;
    for (auto obj : respJson["data"]) {
        auto time_res =
            scheduler::utils::parseIso8601(obj["timestamp"].asString());
        if (!time_res) {
            LOG_ERROR << "Failed to parse timestamp: "
                      << obj["timestamp"].asString();
            continue;
        }
        double load = obj["value"].asDouble();
        loadData.emplace_back(time_res.value(), load);
    }
    return loadData;
}

auto PredictionApi::parseJsonForGreenness(const Json::Value &respJson)
    -> vector<pair<chrono::system_clock::time_point, double>> {
    vector<pair<chrono::system_clock::time_point, double>> greennessData;
    for (auto obj : respJson["data"]) {
        auto time_res =
            scheduler::utils::parseIso8601(obj["timestamp"].asString());
        if (!time_res) {
            LOG_ERROR << "Failed to parse timestamp: "
                      << obj["timestamp"].asString();
            continue;
        }
        double load = obj["value"].asDouble();
        greennessData.emplace_back(time_res.value(), load);
    }
    return greennessData;
}
