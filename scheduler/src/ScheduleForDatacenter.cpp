#include <DatacenterSpecificInformation.hpp>
#include <ScheduleForDatacenter.hpp>
#include <ScheduledInterval.hpp>
#include<iostream>

using namespace std;

void ScheduleForDatacenter::addInterval(ScheduledInterval newInterval)
{
    schedule.insert(newInterval);
}

void ScheduleForDatacenter::show()
{
    cout << datacenterInfo.maxLoad << " " << datacenterInfo.name << ":" << endl;
    cout << "[" << endl ;
    for(auto interval: schedule) interval.show();
    cout << "]" << endl << endl;
}