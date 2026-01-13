#include <ScheduledInterval.hpp>

#include <iostream>
using namespace std;

void ScheduledInterval::show() const {
    cout << timestamp << " " << jobId << " " << additionalLoad << " "
         << totalLoad << ",\n";
}

auto ScheduledInterval::toJson() const -> Json::Value {
    auto intervalJson = Json::Value{};
    intervalJson["timestamp"] = static_cast<Json::Int64>(timestamp);
    intervalJson["jobId"] = jobId;
    intervalJson["additionalLoad"] = additionalLoad;
    intervalJson["totalLoad"] = totalLoad;
    return intervalJson;
}
