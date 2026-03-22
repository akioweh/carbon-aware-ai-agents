# .devcontainer/Dockerfile
FROM archlinux:latest

# 1. Setup keys and packages
RUN pacman-key --init && pacman-key --populate archlinux && \
    pacman -Syu --noconfirm

# 2. Install dev tools and build dependencies
RUN pacman -S --noconfirm \
    base-devel cmake ninja git gdb lldb clang \
    boost onetbb postgresql-libs jsoncpp c-ares brotli zlib util-linux-libs \
    nodejs npm

# 3. Build/Install Drogon (to avoid recompiling in every dev session)
WORKDIR /build-deps
RUN git clone --depth 1 --branch v1.9.11 https://github.com/drogonframework/drogon.git && \
    cd drogon && \
    git submodule update --init && \
    mkdir build && cd build && \
    cmake -DCMAKE_BUILD_TYPE=Debug \
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

# 4. Set shell
RUN echo "PS1='\[\033[01;32m\]\u@dev-container\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '" >> /root/.bashrc

WORKDIR /workspace
