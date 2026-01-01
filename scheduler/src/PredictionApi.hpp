#ifndef PREDICTION_API
#define PREDICTION_API

#include <DatacenterSpecificInformation.hpp>
#include <PredictedDatacenterInformation.hpp>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>
#include <map>
#include <memory>
#include <string>
#include <vector>

class PredictionApi {

  private:
    const std::string host = "http://127.0.0.1:5000";
    auto parseJsonForLoad(const Json::Value &respJson)
        -> std::vector<std::pair<long long, double>>;
    auto parseJsonForGreeness(const Json::Value &respJson)
        -> std::vector<std::pair<long long, double>>;
    auto parseJsonForDCSpecificInfo(const std::string &datacenterName,
                                    const Json::Value &respJson)
        -> DatacenterSpecificInformation;
    auto getDataSingleDatacenter(const std::string &datacenterName)
        -> drogon::Task<std::vector<PredictedDatacenterInformation>>;

    auto makeGetRequest(const std::string &path)
        -> drogon::Task<std::shared_ptr<Json::Value>>;

  public:
    auto getData()
        -> drogon::Task<std::map<int, std::vector<PredictedDatacenterInformation>>>;
};

#endif
