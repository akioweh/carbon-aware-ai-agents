#ifndef PREDICTION_API
#define PREDICTION_API
#pragma once

#include <DatacenterSpecificInformation.hpp>
#include <PredictedDatacenterInformation.hpp>
#include <chrono>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <json/value.h>
#include <map>
#include <string>
#include <vector>

class PredictionApi {

  private:
    const std::string host = "http://127.0.0.1:5000";

    auto parseJsonForLoad(const Json::Value &respJson) -> std::vector<
        std::pair<std::chrono::system_clock::time_point, double>>;
    auto parseJsonForGreenness(const Json::Value &respJson) -> std::vector<
        std::pair<std::chrono::system_clock::time_point, double>>;
    auto getDataSingleDatacenter(const std::string &datacenterName)
        -> drogon::Task<std::vector<PredictedDatacenterInformation>>;
    auto getLoadPath(const std::string &datacenterName) -> std::string;
    auto getGreennessPath(const std::string &datacenterName) -> std::string;
    auto constructDCPredictions(
        std::vector<std::pair<std::chrono::system_clock::time_point, double>>
            &loadData,
        std::vector<std::pair<std::chrono::system_clock::time_point, double>>
            &greennessData,
        DatacenterSpecificInformation &datacenterSpecificInfo)
        -> std::vector<PredictedDatacenterInformation>;

  public:
    auto getData() -> drogon::Task<
        std::map<long long, std::vector<PredictedDatacenterInformation>>>;
};

#endif
