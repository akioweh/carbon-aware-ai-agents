#ifndef SCHEDULER_DATACENTER_IDENTIFIER_HPP
#define SCHEDULER_DATACENTER_IDENTIFIER_HPP
#include "Calendar.hpp"
#include "structs/Datacenter.hpp"
#pragma once

#include "exceptions/ValidationException.hpp"
#include <drogon/HttpRequest.h>
#include <string>

namespace scheduler {
/**
 * @class DatacenterIdentifierParam
 * @brief Datacenter name deserializer from URL parameters.
 */
struct DatacenterIdentifierParam {
    std::string name;
};
} // namespace scheduler

namespace drogon {
template <>
inline auto fromRequest(const HttpRequest &req)
    -> scheduler::DatacenterIdentifierParam {
    const auto &params = req.getParameters();
    auto defaultName = scheduler::calendar::ANY_DATACENTER;
    if (params.contains("datacenter")) {
        defaultName = params.at("datacenter");
    }
    return scheduler::DatacenterIdentifierParam{.name = defaultName};
}
} // namespace drogon

#endif // SCHEDULER_DATACENTER_IDENTIFIER_HPP
