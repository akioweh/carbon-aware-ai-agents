#include<ScheduledInterval.hpp>

#include<iostream>
using namespace std;

void ScheduledInterval::show()
{
    cout << timestamp << " " << jobId << " " << additionalLoad << " " << totalLoad <<  ",\n";
}