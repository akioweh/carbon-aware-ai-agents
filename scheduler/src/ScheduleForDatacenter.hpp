#ifndef SCHEDULE
#define SCHEDULE
#pragma once

#include <DatacenterSpecificInformation.hpp>
#include <ScheduledInterval.hpp>
#include <Serializable.hpp>

#include <set>
#include <utility>

class ScheduleForDatacenter : public Serializable {
  public:
    DatacenterSpecificInformation datacenterInfo;
    std::set<ScheduledInterval> schedule;

    ScheduleForDatacenter(DatacenterSpecificInformation datacenterInfo)
        : datacenterInfo(std::move(datacenterInfo)) {};

    ScheduleForDatacenter() = default;

    void addInterval(ScheduledInterval newInterval);
    void show();
    [[nodiscard]] auto toJson() const -> Json::Value override;
};

#endif
