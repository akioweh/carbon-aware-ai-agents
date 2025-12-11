#ifndef DATACENTER_SPECIFIC_INFORMATION
#define DATACENTER_SPECIFIC_INFORMATION

#include <string>
#include <utility>

class DatacenterSpecificInformation {
  public:
    double maxLoad;
    std::string locationId;
    std::string name;
    std::string region;
    int datacenterId;

    DatacenterSpecificInformation(double maxLoad, std::string locationId,
                                  std::string name, std::string region,
                                  int datacenterId)
        : maxLoad(maxLoad), locationId(std::move(locationId)),
          name(std::move(name)), region(std::move(region)),
          datacenterId(datacenterId) {};

    DatacenterSpecificInformation() = default;
};

#endif
