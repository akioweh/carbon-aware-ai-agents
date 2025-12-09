#ifndef SCHEDULE
#define SCHEDULE

#include<DatacenterSpecificInformation.hpp>
#include<ScheduledInterval.hpp>

#include<set>

class ScheduleForDatacenter
{   
    public:
    DatacenterSpecificInformation datacenterInfo;
    std::set<ScheduledInterval> schedule;

    ScheduleForDatacenter(DatacenterSpecificInformation dataInfo) ;
    void addInterval(ScheduledInterval newInterval);
    void show();
};

#endif