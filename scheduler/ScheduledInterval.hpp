#ifndef SCHEDULED_INTERVAL
#define SCHEDULED_INTERVAL

class ScheduledInterval
{
    public:
    long long timestamp;
    int jobId;
    double additionalLoad; /// thats what we scheduled
    double totalLoad; /// thats what we scheduled + predicted at that time

    bool operator <(const ScheduledInterval &other) const
    {
        return timestamp<other.timestamp;
    }
};

#endif