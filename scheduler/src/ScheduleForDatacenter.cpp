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
