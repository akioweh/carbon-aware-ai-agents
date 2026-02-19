#ifndef SCHEDULER_DATACENTER_IDENTIFIER_HPP
#define SCHEDULER_DATACENTER_IDENTIFIER_HPP
#pragma once

#include "exceptions/ValidationException.hpp"
#include <drogon/HttpRequest.h>
#include <string>

namespace scheduler {
/**
 * @class JobIdentifier
 * @brief Job ID deserializer from URL parameters.
 */
struct DatacenterIdentifierParam {
    std::string datacenter;

    DatacenterIdentifierParam() = default;

    explicit DatacenterIdentifierParam(const std::string &datacenter) {
        if (datacenter.empty())
            throw exceptions::ValidationException("datacenter cannot be empty");
        this->datacenter = datacenter;
    }

    [[nodiscard]] auto getDatacenter() const -> const std::string & {
        return datacenter;
    }
};
} // namespace scheduler

#endif // SCHEDULER_DATACENTER_IDENTIFIER_HPP
