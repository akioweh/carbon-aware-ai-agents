#include <DatacenterSpecificInformation.hpp>
#include <ScheduleForDatacenter.hpp>
#include <ScheduledInterval.hpp>
#include <iostream>

using namespace std;

void ScheduleForDatacenter::addInterval(ScheduledInterval newInterval) {
    schedule.insert(newInterval);
}

void ScheduleForDatacenter::show() {
    cout << datacenterInfo.maxLoad << " " << datacenterInfo.name << ":" << '\n';
    cout << "[" << '\n';
    for (auto interval : schedule) {
        interval.show();
    }
    cout << "]" << '\n' << '\n';
}

auto ScheduleForDatacenter::toJson() const -> Json::Value {
    auto dcJson = Json::Value{};
    dcJson["datacenterInfo"] = datacenterInfo.toJson();
    auto intervalsJson = Json::Value(Json::arrayValue);
    for (const auto &interval : schedule) {
        intervalsJson.append(interval.toJson());
    }
    dcJson["intervals"] = intervalsJson;
    return dcJson;
}
