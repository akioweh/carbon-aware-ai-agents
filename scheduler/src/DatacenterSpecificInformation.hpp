#ifndef DATACENTER_SPECIFIC_INFORMATION
#define DATACENTER_SPECIFIC_INFORMATION

#include <Serializable.hpp>
#include <string>
#include <utility>

class DatacenterSpecificInformation : public Serializable {
  public:
    double maxLoad;
    std::string locationId;
    std::string name;
    std::string region;
    long long datacenterId;

    DatacenterSpecificInformation(double maxLoad, std::string locationId,
                                  std::string name, std::string region,
                                  long long datacenterId)
        : maxLoad(maxLoad), locationId(std::move(locationId)),
          name(std::move(name)), region(std::move(region)),
          datacenterId(datacenterId) {};

    DatacenterSpecificInformation() = default;

    static auto parseJsonForDCSpecificInfo(const std::string &datacenterName,
                                           const Json::Value &respJson)
        -> DatacenterSpecificInformation;

    [[nodiscard]] auto toJson() const -> Json::Value override;
};

#endif
