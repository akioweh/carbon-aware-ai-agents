#include <DatacenterSpecificInformation.hpp>

using namespace std;

DatacenterSpecificInformation::DatacenterSpecificInformation(double maxLoad, int datacenterId,
                                                             string locationId, string name,
                                                             string region)
    : maxLoad(maxLoad), datacenterId(datacenterId), locationId(locationId), name(name),
      region(region) {};
