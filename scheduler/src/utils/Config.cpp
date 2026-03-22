#include "Config.hpp"
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <string_view>
#include <trantor/utils/Logger.h>

namespace scheduler::utils {

namespace {

/**
 * @brief Overrides a JSON node value from an environment variable if it exists.
 *
 * Supports integer, boolean, and string (default) types.
 */
void overrideFromEnv(Json::Value &node, const char *env_var) {
    const char *val = std::getenv(env_var);
    if (val == nullptr || strlen(val) == 0)
        return;

    if (node.isIntegral()) {
        try {
            node = std::stoi(val);
        } catch (...) {
            LOG_ERROR << "Config Error: Failed to convert env " << env_var
                      << " (" << val << ") to integer.\n";
        }
    } else if (node.isBool()) {
        using namespace std::literals;
        node = (val == "true"sv || val == "1"sv || val == "yes"sv);
    } else {
        node = val;
    }
}

void error_and_exit(const std::string &message) {
    LOG_ERROR << "Config Error: " << message << "\n";
    std::exit(EXIT_FAILURE);
}

} // namespace

auto loadConfig(const std::string &path) -> Json::Value {
    auto config = Json::Value{};
    auto ifs = std::ifstream(path);

    if (ifs.is_open()) {
        auto builder = Json::CharReaderBuilder{};
        builder["collectComments"] = false;
        auto errs = std::string{};
        if (!Json::parseFromStream(builder, ifs, &config, &errs))
            error_and_exit("Failed to parse " + path + ": " + errs);
    } else {
        error_and_exit("Could not open config file: " + path);
    }

    if (!config.isMember("app"))
        error_and_exit("Missing required 'app' configuration section.");

    if (!config["app"].isMember("threads_num"))
        config["app"]["threads_num"] = 0;
    overrideFromEnv(config["app"]["threads_num"], "THREADS");

    if (!config.isMember("listeners") || !config["listeners"].isArray())
        error_and_exit("Missing required 'listeners' entry in configuration.");
    if (config["listeners"].empty()) {
        config["listeners"].append(Json::Value(Json::objectValue));
        config["listeners"][0]["address"] = "0.0.0.0";
        config["listeners"][0]["port"] = DEFAULT_PORT;
        config["listeners"][0]["https"] = false;
    }
    auto &listener = config["listeners"][0];
    overrideFromEnv(listener["port"], "PORT");

    if (!config.isMember("db_clients") || !config["db_clients"].isArray())
        error_and_exit("Missing required 'db_clients' entry in configuration.");
    if (config["db_clients"].empty())
        config["db_clients"].append(Json::Value(Json::objectValue));
    auto &db = config["db_clients"][0];

    overrideFromEnv(db["host"], "PGHOST");
    overrideFromEnv(db["port"], "PGPORT");
    overrideFromEnv(db["dbname"], "PGDATABASE");
    overrideFromEnv(db["user"], "PGUSER");
    overrideFromEnv(db["passwd"], "PGPASSWORD");

    return config;
}

} // namespace scheduler::utils
