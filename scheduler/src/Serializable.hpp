#ifndef SCHEDULER_SERIALIZABLE_HPP
#define SCHEDULER_SERIALIZABLE_HPP
#include <concepts>
#pragma once
#include <json/value.h>
#include <map>
#include <optional>
#include <string>
#include <vector>

// overloads for primitive types
inline auto f_toJson(const char *v) -> Json::Value { return v; }
inline auto f_toJson(const std::string &v) -> Json::Value { return v; }
inline auto f_toJson(bool v) -> Json::Value { return v; }
template <std::integral T> inline auto f_toJson(T v) -> Json::Value {
    if constexpr (std::is_signed_v<T>)
        return static_cast<Json::Int64>(v);
    else
        return static_cast<Json::UInt64>(v);
}
template <std::floating_point T> inline auto f_toJson(T v) -> Json::Value {
    return static_cast<double>(v);
}

// overloads for stl containers: vector
template <typename T>
    requires requires(const T &obj) {
        { f_toJson(obj) } -> std::convertible_to<Json::Value>;
    }
inline auto f_toJson(const std::vector<T> &vec) -> Json::Value {
    auto res = Json::Value(Json::arrayValue);
    for (const auto &elem : vec)
        res.append(f_toJson(elem));
    return res;
}

// overloads for stl containers: map
template <typename K, typename V>
    requires requires(const V &obj) {
        { f_toJson(obj) } -> std::convertible_to<Json::Value>;
    } && (requires(const Json::Value &json, const K &key) { json[key]; } ||
          std::convertible_to<K, std::string>)
inline auto f_toJson(const std::map<K, V> &m) -> Json::Value {
    auto res = Json::Value(Json::objectValue);
    for (const auto &[key, value] : m)
        res[key] = f_toJson(value);
    return res;
}

// overloads for stl containers: optional
template <typename T>
    requires requires(const T &obj) {
        { f_toJson(obj) } -> std::convertible_to<Json::Value>;
    }
inline auto f_toJson(const std::optional<T> &opt) -> Json::Value {
    if (opt.has_value())
        return f_toJson(opt.value());
    return {Json::nullValue};
}

/// note that the above HAVE to be defined before the concept.
/// (because we cannot use ADL for primitives or the std namespace)

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
