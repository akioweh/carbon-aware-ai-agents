#include "DatacenterSpecificInformation.hpp"

using namespace std;

auto DatacenterSpecificInformation::parseJsonForDCSpecificInfo(
    const std::string &datacenterName, const Json::Value &respJson)
    -> DatacenterSpecificInformation {
    double maxLoad = respJson["capacity"]["max_load"].asDouble();
    hash<string> hasher;
    return {maxLoad, "not defined yet", datacenterName, "not defined yet",
            static_cast<long long>(hasher(datacenterName))};
    // we want to be stateless, and the python api is not providing id, so I
    // just generate id as a hash of name. we technically can just use names as
    // ids but for now i wanted to stick with the id as numbers.
}

auto DatacenterSpecificInformation::toJson() const -> Json::Value {
    Json::Value infoJson;
    infoJson["maxLoad"] = maxLoad;
    infoJson["locationId"] = locationId;
    infoJson["name"] = name;
    infoJson["region"] = region;
    infoJson["datacenterId"] = static_cast<Json::Int64>(datacenterId);
    return infoJson;
}
