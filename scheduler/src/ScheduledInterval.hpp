#ifndef SCHEDULED_INTERVAL
#define SCHEDULED_INTERVAL

class ScheduledInterval
{
    public:
    long long timestamp;
    int jobId;
    double additionalLoad; /// thats what we scheduled
    double totalLoad; /// thats what we scheduled + predicted at that time

    ScheduledInterval(long long timestep, int jobId, double additionalLoad, double totalLoad)
    : timestamp(timestamp), jobId(jobId), additionalLoad(additionalLoad), totalLoad(totalLoad) {} ;

    bool operator <(const ScheduledInterval &other) const
    {
        return timestamp<other.timestamp;
    }

    void show(); 
};

#endif