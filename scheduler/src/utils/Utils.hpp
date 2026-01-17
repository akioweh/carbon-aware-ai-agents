#ifndef UTILS
#define UTILS

#include <chrono>
#include <drogon/drogon.h>
#include <drogon/utils/coroutine.h>
#include <expected>
#include <json/value.h>
#include <string>

namespace scheduler::utils {
auto parseIso8601(const std::string &timestamp)
    -> std::expected<std::chrono::system_clock::time_point, std::string>;
auto toIso8601(const std::chrono::system_clock::time_point &timePoint)
    -> std::string;

auto makeGetRequest(const std::string &host, const std::string &path)
    -> drogon::Task<std::shared_ptr<Json::Value>>;

// "Protected" call that captures exceptions if any are thrown
// using std::expected
template <typename Func>
    requires std::is_invocable_v<Func>
auto pcall(Func &&func) -> std::expected<decltype(func()), std::exception_ptr> {
    using return_t = decltype(func());
    try {
        if constexpr (std::is_void_v<return_t>) {
            func();
            return {};
        } else {
            return func();
        }
    } catch (...) {
        return std::unexpected(std::current_exception());
    }
}
}; // namespace scheduler::utils

#endif
