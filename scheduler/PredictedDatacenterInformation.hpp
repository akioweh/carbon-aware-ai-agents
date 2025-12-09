#ifndef PREDICTED_DATACENTER_INFORMATION
#define PREDICTED_DATACENTER_INFORMATION

#include <DatacenterSpecificInformation.hpp>

class PredictedDatacenterInformation
{
  public:
    long long timestamp;
    double currentLoad;
    double currentGreenness;
    DatacenterSpecificInformation datacenterSpecificInformation;
};

#endif