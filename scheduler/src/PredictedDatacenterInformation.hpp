#ifndef PREDICTED_DATACENTER_INFORMATION
#define PREDICTED_DATACENTER_INFORMATION

#include <DatacenterSpecificInformation.hpp>
#include <utility>

class PredictedDatacenterInformation {
  public:
    long long timestamp;
    long long lengthOfInterval;
    double currentLoad;
    double currentGreenness;
    DatacenterSpecificInformation datacenterInfo;

    PredictedDatacenterInformation(long long timestamp,
                                   long long lengthOfInterval,
                                   double currentLoad, double currentGreenness,
                                   DatacenterSpecificInformation datacenterInfo)
        : timestamp(timestamp), lengthOfInterval(lengthOfInterval),
          currentLoad(currentLoad), currentGreenness(currentGreenness),
          datacenterInfo(std::move(datacenterInfo)) {};

    auto operator<(const PredictedDatacenterInformation &other) const -> bool {
        return currentGreenness < other.currentGreenness;
    }
};

#endif
