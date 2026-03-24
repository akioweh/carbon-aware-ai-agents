FROM archlinux:latest AS deps
RUN pacman-key --init && pacman-key --populate archlinux
RUN --mount=type=cache,target=/var/cache/pacman \
    pacman -Syu --noconfirm && \
    pacman -S --noconfirm base-devel cmake ninja git boost onetbb postgresql-libs jsoncpp c-ares brotli zlib util-linux-libs ccache

# Build Drogon
WORKDIR /build-deps
RUN git clone --depth 1 --branch v1.9.11 https://github.com/drogonframework/drogon.git && \
    cd drogon && \
    git submodule update --init && \
    mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Release \
          -DCMAKE_CXX_FLAGS="-march=x86-64" \
          -DCMAKE_C_FLAGS="-march=x86-64" \
          -DBUILD_EXAMPLES=OFF \
          -DBUILD_TESTING=OFF \
          -DBUILD_TRANTOR=ON \
          -DBUILD_REDIS=OFF \
          -DBUILD_MYSQL=OFF \
          -DBUILD_SQLITE=OFF \
          -DBUILD_YAML_CONFIG=OFF \
          -DCMAKE_INSTALL_PREFIX=/usr/local \
          -G Ninja .. && \
    ninja install

FROM deps AS builder
WORKDIR /app
COPY . .

# Use ccache for fast, reliable object-level caching without stale build artifacts
RUN --mount=type=cache,target=/root/.cache/ccache \
    cmake --preset arch-generic-rel -DBUILD_TESTING=OFF && \
    cmake --build build/arch-generic-rel --target scheduler && \
    mkdir -p /app/dist && \
    cp build/arch-generic-rel/scheduler /app/dist/

FROM archlinux:latest
RUN pacman-key --init && pacman-key --populate archlinux
RUN --mount=type=cache,target=/var/cache/pacman \
    pacman -Syu --noconfirm && \
    pacman -S --noconfirm boost-libs onetbb postgresql-libs jsoncpp c-ares brotli zlib util-linux-libs && \
    pacman -Scc --noconfirm

WORKDIR /app
COPY --from=builder /app/dist/scheduler .
COPY --from=builder /app/config.json .

EXPOSE 6969
CMD ["./scheduler"]
