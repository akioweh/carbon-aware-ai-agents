#include <ScheduledInterval.hpp>

#include <iostream>
using namespace std;

void ScheduledInterval::show() const {
    cout << timestamp << " " << jobId << " " << additionalLoad << " "
         << totalLoad << ",\n";
}

auto ScheduledInterval::toJson() const -> Json::Value {
    Json::Value intervalJson;
    intervalJson["timestamp"] = (Json::Int64)timestamp;
    intervalJson["jobId"] = jobId;
    intervalJson["additionalLoad"] = additionalLoad;
    intervalJson["totalLoad"] = totalLoad;
    return intervalJson;
}
