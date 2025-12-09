#ifndef DATACENTER_SPECIFIC_INFORMATION
#define DATACENTER_SPECIFIC_INFORMATION

#include <string>

class DatacenterSpecificInformation
{
  public:
    double maxLoad;
    std::string locationId;
    std::string name;
    std::string region;
    int datacenterId;

    DatacenterSpecificInformation(double maxLoad, std::string locationId, std::string name,
                                  std::string region, int datacenterId)
        : maxLoad(maxLoad), locationId(locationId), name(name), region(region), datacenterId(datacenterId) {};
    
    DatacenterSpecificInformation() {} ;
};

#endif