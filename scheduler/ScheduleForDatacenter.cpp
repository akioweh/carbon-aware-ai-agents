#include <DatacenterSpecificInformation.hpp>
#include <ScheduleForDatacenter.hpp>
#include <ScheduledInterval.hpp>

using namespace std;

ScheduleForDatacenter::ScheduleForDatacenter(DatacenterSpecificInformation dataInfo)
    : datacenterInfo(datacenterInfo) {};

void ScheduleForDatacenter::addInterval(ScheduledInterval newInterval)
{
    schedule.insert(newInterval);
}