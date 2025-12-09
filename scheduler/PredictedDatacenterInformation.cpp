#include <PredictedDatacenterInformation.hpp>

PredictedDatacenterInformation::PredictedDatacenterInformation(
    long long timestamp, double currentLoad,
    DatacenterSpecificInformation datacenterSpecificInformation)
    : timestamp(timestamp), currentLoad(currentLoad),
      datacenterSpecificInformation(datacenterSpecificInformation) {};