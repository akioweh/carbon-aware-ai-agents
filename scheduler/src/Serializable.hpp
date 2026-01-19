#ifndef SERIALIZABLE_HPP
#define SERIALIZABLE_HPP
#pragma once

#include <json/value.h>

template <typename T>
concept Serializable = requires(const T &obj) {
    { toJson(obj) } -> std::convertible_to<Json::Value>;
};

#endif
