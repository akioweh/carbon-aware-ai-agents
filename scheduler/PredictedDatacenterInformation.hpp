#ifndef PREDICTED_DATACENTER_INFORMATION
#define PREDICTED_DATACENTER_INFORMATION

#include <DatacenterSpecificInformation.hpp>

class PredictedDatacenterInformation
{
  private:
    long long timestamp;
    double currentLoad;
    double currentGreenness;
    DatacenterSpecificInformation datacenterSpecificInformation;

    PredictedDatacenterInformation(long long timestamp, double currentLoad,
                                   DatacenterSpecificInformation datacenterSpecificInformation);
};

#endif