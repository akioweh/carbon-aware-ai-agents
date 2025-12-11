#ifndef SCHEDULED_INTERVAL
#define SCHEDULED_INTERVAL

class ScheduledInterval {
  public:
    long long timestamp;
    int jobId;
    double additionalLoad; /// thats what we scheduled
    double totalLoad;      /// thats what we scheduled + predicted at that time

    ScheduledInterval(long long timestamp, int jobId, double additionalLoad,
                      double totalLoad)
        : timestamp(timestamp), jobId(jobId), additionalLoad(additionalLoad),
          totalLoad(totalLoad) {};

    auto operator<(const ScheduledInterval &other) const -> bool {
        return timestamp < other.timestamp;
    }

    void show() const;
};

#endif
