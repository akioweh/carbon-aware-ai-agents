#ifndef PREDICTED_DATACENTER_INFORMATION
#define PREDICTED_DATACENTER_INFORMATION

#include <DatacenterSpecificInformation.hpp>

class PredictedDatacenterInformation
{
  public:
    long long timestamp;
    long long lengthOfInterval;
    double currentLoad;
    double currentGreenness;
    DatacenterSpecificInformation datacenterInfo;

    PredictedDatacenterInformation(long long timestamp, long long lengthOfInterval,
                                   double currentLoad, double currentGreenness,
                                   DatacenterSpecificInformation datacenterInfo)
        : timestamp(timestamp), lengthOfInterval(lengthOfInterval), currentLoad(currentLoad),
          currentGreenness(currentGreenness), datacenterInfo(datacenterInfo) {};

    bool operator<(const PredictedDatacenterInformation &other) const
    {
        return currentGreenness < other.currentGreenness;
    }
};

#endif