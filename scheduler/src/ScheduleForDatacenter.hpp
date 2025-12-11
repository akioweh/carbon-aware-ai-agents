#ifndef SCHEDULE
#define SCHEDULE

#include <DatacenterSpecificInformation.hpp>
#include <ScheduledInterval.hpp>

#include <set>
#include <utility>

class ScheduleForDatacenter {
  public:
    DatacenterSpecificInformation datacenterInfo;
    std::set<ScheduledInterval> schedule;

    ScheduleForDatacenter(DatacenterSpecificInformation datacenterInfo)
        : datacenterInfo(std::move(datacenterInfo)) {};

    ScheduleForDatacenter() = default;

    void addInterval(ScheduledInterval newInterval);
    void show();
};

#endif
