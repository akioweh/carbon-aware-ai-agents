#ifndef SCHEDULER_CONFIG_HPP
#define SCHEDULER_CONFIG_HPP
#pragma once

#include <json/json.h>
#include <string>

namespace scheduler {

constexpr auto DEFAULT_PORT = 6969;

namespace utils {

/**
 * @brief Configuration loader for the scheduler application.
 *
 * This utility loads the base JSON configuration from a file and applies
 * potential overrides from environment variables.
 */
auto loadConfig(const std::string &path) -> Json::Value;

} // namespace utils

} // namespace scheduler

#endif // SCHEDULER_CONFIG_HPP
