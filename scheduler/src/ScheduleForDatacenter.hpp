#ifndef SCHEDULE
#define SCHEDULE
#pragma once

#include <DatacenterSpecificInformation.hpp>
#include <ScheduledInterval.hpp>
#include <Serializable.hpp>

#include <set>
#include <utility>

class ScheduleForDatacenter {
  public:
    DatacenterSpecificInformation datacenterInfo;
    std::set<ScheduledInterval> schedule;

    ScheduleForDatacenter(DatacenterSpecificInformation datacenterInfo)
        : datacenterInfo(std::move(datacenterInfo)) {};

    ScheduleForDatacenter() = default;

    void addInterval(const ScheduledInterval &newInterval);
    void show();
};

auto f_toJson(const ScheduleForDatacenter &obj) -> Json::Value;

static_assert(Serializable<ScheduleForDatacenter>);

#endif
