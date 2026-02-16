#ifndef SCHEDULER_SERIALIZABLE_HPP
#define SCHEDULER_SERIALIZABLE_HPP
#pragma once

#include <json/value.h>

/**
 * @brief Types that can be serialized to JSON via a f_toJson
 * function.
 */
template <typename T>
concept Serializable = requires(const T &obj) {
    { f_toJson(obj) } -> std::convertible_to<Json::Value>;
};

namespace scheduler::serialization::impl {
struct toJsonFn {
    auto operator()(const Serializable auto &obj) const -> auto {
        return f_toJson(obj);
    }
};
} // namespace scheduler::serialization::impl

/**
 * @brief Niebloid deferring f_toJson OVL.
 *
 * For a type to participate in serialization via toJson,
 * it must be \ref Serializable (i.e. have a f_toJson overload).
 */
inline constexpr scheduler::serialization::impl::toJsonFn toJson{};

#endif // SCHEDULER_SERIALIZABLE_HPP
