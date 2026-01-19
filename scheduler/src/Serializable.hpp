#ifndef SERIALIZABLE_HPP
#define SERIALIZABLE_HPP
#pragma once

#include <json/value.h>

template <typename T>
concept Serializable = requires(const T &obj) {
    { f_toJson(obj) } -> std::convertible_to<Json::Value>;
};

struct toJsonFn {
    auto operator()(const Serializable auto &obj) const -> auto {
        return f_toJson(obj);
    }
};

inline constexpr toJsonFn toJson{};

#endif
