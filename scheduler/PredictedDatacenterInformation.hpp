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

  public:
    PredictedDatacenterInformation(long long timestamp, double currentLoad,
                                   DatacenterSpecificInformation datacenterSpecificInformation);

    long long getTimestamp()
    {
        return timestamp;
    }

    double getCurrentLoad()
    {
        return currentLoad;
    }

    double getCurrentGreeness()
    {
        return currentGreenness;
    }

    DatacenterSpecificInformation getDatacenterSpecificInformation()
    {
        return datacenterSpecificInformation;
    }
};

#endif