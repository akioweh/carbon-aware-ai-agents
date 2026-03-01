#ifndef SCHEDULER_SERIALIZABLE_HPP
#define SCHEDULER_SERIALIZABLE_HPP
#pragma once

#include <json/value.h>

template <typename T> auto f_toJson(const std::vector<T> &V) -> Json::Value;

/**
 * @brief Types that can be serialized to JSON via a f_toJson
 * function.
 */
template <typename T>
concept BaseSerializable = requires(const T &obj) {
    { f_toJson(obj) } -> std::convertible_to<Json::Value>;
};

template <typename T>
concept VectorSerializable = requires(const T &obj) {
    typename T::value_type;
    requires BaseSerializable<typename T::value_type>;
};

template <typename T>
concept Serializable = BaseSerializable<T> || VectorSerializable<T>;

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

template <typename T>
    requires Serializable<T>
inline auto f_toJson(const std::vector<T> &V) -> Json::Value {
    auto res = Json::Value(Json::arrayValue);
    for (const auto &val : V) {
        res.append(toJson(val));
    }
    return res;
}

#endif // SCHEDULER_SERIALIZABLE_HPP
