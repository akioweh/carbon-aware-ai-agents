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

    bool operator<(const PredictedDatacenterInformation &other) const
    {
        return currentGreenness < other.currentGreenness;
    }
};

#endif