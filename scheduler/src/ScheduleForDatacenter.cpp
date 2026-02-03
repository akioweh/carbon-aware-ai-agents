#include <DatacenterSpecificInformation.hpp>
#include <ScheduleForDatacenter.hpp>
#include <ScheduledInterval.hpp>
#include <iostream>

using namespace std;

void ScheduleForDatacenter::addInterval(const ScheduledInterval &newInterval) {
    schedule.insert(newInterval);
}

void ScheduleForDatacenter::show() {
    cout << datacenterInfo.maxLoad << " " << datacenterInfo.name << ":" << '\n';
    cout << "[" << '\n';
    for (const auto &interval : schedule)
        interval.show();
    cout << "]" << '\n' << '\n';
}

auto f_toJson(const ScheduleForDatacenter &obj) -> Json::Value {
    auto res = Json::Value{};
    res["datacenterInfo"] = toJson(obj.datacenterInfo);
    auto intervalsJson = Json::Value(Json::arrayValue);
    for (const auto &interval : obj.schedule)
        intervalsJson.append(toJson(interval));
    res["intervals"] = intervalsJson;
    return res;
}
