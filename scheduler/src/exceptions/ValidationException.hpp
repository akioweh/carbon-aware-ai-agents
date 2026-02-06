#ifndef VALIDATION_EXCEPTION_HPP
#define VALIDATION_EXCEPTION_HPP
#pragma once

#include <exception>
#include <string>
#include <utility>

namespace scheduler::exceptions {

class ValidationException : public std::exception {
  public:
    explicit ValidationException(std::string message)
        : message_(std::move(message)) {}

    [[nodiscard]] auto what() const noexcept -> const char * override {
        return message_.c_str();
    }

  private:
    std::string message_;
};

} // namespace scheduler::exceptions

#endif
