#ifndef DATACENTER_SPECIFIC_INFORMATION
#define DATACENTER_SPECIFIC_INFORMATION

#include <string>

class DatacenterSpecificInformation
{
  private:
    double maxLoad;
    std::string locationId;
    std::string name;
    std::string region;
    int datacenterId;

  public:
    DatacenterSpecificInformation(double maxLoad, int datacenterId, std::string locationId,
                                  std::string name, std::string region);

    double getMaxLoad()
    {
        return maxLoad;
    }

    std::string getLocationId()
    {
        return locationId;
    }

    std::string getName()
    {
        return name;
    }

    std::string getRegion()
    {
        return region;
    }
    
    int getDatacenterId()
    {
        return datacenterId;
    }
};

#endif