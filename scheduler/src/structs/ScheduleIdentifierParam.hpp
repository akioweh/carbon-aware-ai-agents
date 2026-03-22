#ifndef SCHEDULER_SCHEDULE_IDENTIFIER_HPP
#define SCHEDULER_SCHEDULE_IDENTIFIER_HPP
#pragma once

#include "exceptions/ValidationException.hpp"
#include <drogon/HttpRequest.h>
#include <string>

namespace scheduler {

/**
 * @class JobIdentifier
 * @brief Job ID deserializer from URL parameters.
 */
struct ScheduleIdentifierParam {
    std::string scheduleId;

    ScheduleIdentifierParam() = default;

    explicit ScheduleIdentifierParam(const std::string &scheduleId) {
        if (scheduleId.empty())
            throw exceptions::ValidationException(
                "schedule_id cannot be empty");
        this->scheduleId = scheduleId;
    }

    [[nodiscard]] auto getScheduleId() const -> const std::string & {
        return scheduleId;
    }
};

} // namespace scheduler

#endif // SCHEDULER_SCHEDULE_IDENTIFIER_HPP
