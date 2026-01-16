#ifndef SERIALIZABLE_HPP
#define SERIALIZABLE_HPP
#pragma once

#include <json/value.h>

class Serializable {
  public:
    virtual ~Serializable() = default;
    [[nodiscard]] virtual auto toJson() const -> Json::Value = 0;
};

#endif
