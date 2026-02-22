#ifndef SCHEDULER_NETWORK_EXCEPTION_HPP
#define SCHEDULER_NETWORK_EXCEPTION_HPP
#pragma once

#include <exception>
#include <string>
#include <utility>

namespace scheduler::exceptions {

/**
 * @class NetworkException
 * @brief Thrown when a we cannot connect to Python prediction API.
 *
 * Here everything is fine with the format of the request, we just cannot get
 * the data necessary for scheduling.
 */
class NetworkException : public std::exception {
  public:
    explicit NetworkException(std::string message)
        : message_(std::move(message)) {}

    [[nodiscard]] auto what() const noexcept -> const char * override {
        return message_.c_str();
    }

  private:
    std::string message_;
};

} // namespace scheduler::exceptions

#endif // SCHEDULER_NETWORK_EXCEPTION_HPP
