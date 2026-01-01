#include "PredictedDatacenterInformation.hpp"
#include <DatacenterSpecificInformation.hpp>
#include <PredictionApi.hpp>
#include <drogon/HttpClient.h>
#include <drogon/HttpRequest.h>
#include <drogon/HttpResponse.h>
#include <drogon/HttpTypes.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>
#include <memory>
#include <sstream>
#include <trantor/utils/Logger.h>

using namespace std;
using namespace drogon;

auto PredictionApi::getDataSingleDatacenter(const string &datacenterName)
    -> Task<vector<PredictedDatacenterInformation>> {
    const string loadPath =
        "/locations/" + datacenterName + "/metrics/forecast_load";
    const string greenneesPath =
        "/locations/" + datacenterName + "/metrics/forecast_greenness";

    auto loadJsonPromise = makeGetRequest(loadPath);
    auto greenneesJsonPromise = makeGetRequest(greenneesPath);

    // auto [loadJsonPtr, greenneesJsonPtr] = co_await when_all(loadJsonPromise, greenneesJsonPromise) ;
    // later I will write my own when_all to make this sexy pretty

    auto [loadJsonPtr, greenneesJsonPtr] =
        tuple{co_await loadJsonPromise, co_await greenneesJsonPromise};

    auto loadData = parseJsonForLoad(*loadJsonPtr);
    auto greenessData = parseJsonForGreeness(*greenneesJsonPtr);
    auto datacenterSpecificInfo = parseJsonForDCSpecificInfo(datacenterName, *loadJsonPtr);

    sort(loadData.begin(), loadData.end());
    sort(greenessData.begin(), greenessData.end());
    // sorting after timestamps

    long long lengthOfInterval = loadData[1].first - loadData[0].first;

    vector<PredictedDatacenterInformation> DCInfo;

    for (int i = 0; i < min(greenessData.size(), loadData.size()); i++) {
        auto [timestamp, predictedLoad] = loadData[i];
        auto [dummy, predictedGreeness] = greenessData[i];
        DCInfo.push_back(PredictedDatacenterInformation(
            timestamp, lengthOfInterval, predictedLoad, predictedGreeness,
            datacenterSpecificInfo));
    }

    co_return DCInfo; 
}

auto PredictionApi::getData() -> drogon::Task<
        map<int, vector<PredictedDatacenterInformation>>>
{
    vector<string>datacenterNamesList = {"Data-Center-1", "Data-Center-2", "Data-Center-3", "Data-Center-4", "Data-Center-5"} ;
    // this will be made an API call to get the names. It just isnt implemented yet.

    vector<Task<vector<PredictedDatacenterInformation>>> promisedData ;
    for(auto &name: datacenterNamesList) promisedData.push_back(getDataSingleDatacenter(name)) ;

    map<int,vector<PredictedDatacenterInformation>>data ;
    for(auto &tasks: promisedData)
    {
        auto dcData = co_await tasks; 
        data[dcData.front().datacenterInfo.datacenterId] = dcData ;
    }
    co_return data;
}

auto PredictionApi::parseJsonForDCSpecificInfo(const string &datacenterName, const Json::Value &respJson) -> DatacenterSpecificInformation
{
    double maxLoad = respJson["capacity"]["max_load"].asDouble() ;
    hash<string> hasher; 
    return {maxLoad, "not defined yet", datacenterName, "not defined yet", static_cast<long long>(hasher(datacenterName))} ;
    // we want to be stateless, and the python api is not providing id, so I just generate id as a hash of name.
    // we technically can just use names as ids but for now i wanted to stick with the id as numbers.
}

long long parseTimestampSeconds(const string &timestamp)
{
    // chatgpted - later i can try importing Howard Hinnant’s date library
    // also i will probably move this to a utils package
    std::string datetime = timestamp.substr(0, 19);
    std::tm tm = {};
    std::istringstream ss(datetime);
    ss >> std::get_time(&tm, "%Y-%m-%dT%H:%M:%S");
    std::time_t tt = timegm(&tm); 
    return static_cast<long long>(tt);
}

auto PredictionApi::parseJsonForLoad(const Json::Value &respJson) -> vector<pair<long long, double>>
{
    vector<pair<long long, double>> loadData ;
    for(auto obj: respJson["data"])
    {
        long long timestamp = parseTimestampSeconds(obj["timestamp"].asString());
        double load = obj["value"].asDouble();
        loadData.push_back({timestamp,load}) ;
    }
    return loadData;
}

auto PredictionApi::parseJsonForGreeness(const Json::Value &respJson) -> vector<pair<long long, double>>
{
    vector<pair<long long, double>> greenessData ;
    for(auto obj: respJson["data"])
    {
        long long timestamp = parseTimestampSeconds(obj["timestamp"].asString());
        double load = obj["value"].asDouble();
        greenessData.push_back({timestamp,load}) ;
    }
    return greenessData;
}

auto PredictionApi::makeGetRequest(const string &path)
    -> Task<shared_ptr<Json::Value>> {
    auto client = HttpClient::newHttpClient(host);
    auto request = HttpRequest::newHttpRequest();
    request->setMethod(Get);
    request->setPath(path);

    HttpResponsePtr response;
    try {
        response = co_await client->sendRequestCoro(request);

    } catch (const exception &e) {
        LOG_ERROR << "something is not yes, maybe run python API? XD "
                  << e.what();
        co_return NULL;
    }

    if (!response || response->getStatusCode() != drogon::k200OK) {
        LOG_ERROR << "response is null or has a code different than 200" ;
        co_return NULL;
    }

    auto jsonResponsePtr = response->jsonObject();
    if (!jsonResponsePtr) {
        LOG_ERROR << "couldnt transform to JSON the response" ;
        co_return NULL;
    }

    co_return make_shared<Json::Value>(*jsonResponsePtr);
}
