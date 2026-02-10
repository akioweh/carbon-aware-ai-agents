#ifndef SCHEDULER_JOB_IDENTIFIER_HPP
#define SCHEDULER_JOB_IDENTIFIER_HPP
#pragma once

#include "exceptions/ValidationException.hpp"
#include <drogon/HttpRequest.h>
#include <string>

namespace scheduler {
/**
 * @class JobIdentifier
 * @brief Job ID deserializer from URL parameters.
 */
struct JobIdentifierParam {
    std::string jobId;

    JobIdentifierParam() = default;

    explicit JobIdentifierParam(const std::string &jobId) {
        if (jobId.empty())
            throw exceptions::ValidationException("job_id cannot be empty");
        this->jobId = jobId;
    }

    [[nodiscard]] auto getJobId() const -> const std::string & { return jobId; }
};
} // namespace scheduler

#endif // SCHEDULER_JOB_IDENTIFIER_HPP
