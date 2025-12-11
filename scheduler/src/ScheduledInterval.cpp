#include <ScheduledInterval.hpp>

#include <iostream>
using namespace std;

void ScheduledInterval::show() const {
    cout << timestamp << " " << jobId << " " << additionalLoad << " "
         << totalLoad << ",\n";
}
