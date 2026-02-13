#ifndef SCHEDULER_SCHEDULING_EXCEPTION_HPP
#define SCHEDULER_SCHEDULING_EXCEPTION_HPP
#pragma once

#include <exception>
#include <string>
#include <utility>

namespace scheduler::exceptions {

/**
 * @class SchedulingException
 * @brief Thrown when a valid scheduling request cannot be fulfilled due to
 * resource constraints or system state (maps to HTTP 409 Conflict).
 *
 * This is distinct from ValidationException (422): here, the request is
 * well-formed but the scheduler cannot satisfy it given the current state
 * (e.g. insufficient capacity, no available locations, infeasible workload).
 */
class SchedulingException : public std::exception {
  public:
    explicit SchedulingException(std::string message)
        : message_(std::move(message)) {}

    [[nodiscard]] auto what() const noexcept -> const char * override {
        return message_.c_str();
    }

  private:
    std::string message_;
};

} // namespace scheduler::exceptions

#endif // SCHEDULER_SCHEDULING_EXCEPTION_HPP
