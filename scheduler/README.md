# Scheduler Component

## Development Setup

### Software

C++23!  
Application code should maximally leverage the newest (up to std++23) language and
STL features!

**Library Dependencies:**

- `drogon` (latest stable)
- `boost` (latest stable)

### Toolchain

CMake-based C++.

Tested working configurations:

- Windows \[MSys2 (toolchain) + `vcpkg` (package manager)\]: was not fun to get working
- Arch \[`drogon` via paru\]

If you are developing on a new platform/setup and think a generic version of your
CMake configuration could be used by others too, add it to [`CMakePresets.json`](./CMakePresets.json)!  
However, remember that your personal CMake configurations (like hard-coded paths)
should live in the (untracked) `CMakeUserPresets.json`.

For consistent ergonomics, use `clangd` with `clang-tidy` and `clang-format`.
Their configuration files are tracked for consistent linting and formatting

### Quickstart

0. Ensure your have a working toolchain and the two dependencies installed
1. Find your appropriate preset in [`CMakePresets.json`](./CMakePresets.json) or add what's missing
2. Run `cmake --preset <preset name>` (in this directory) to generate build files
3. Your editor should detect project settings now from [`compile_commands.json`](./compile_commands.json)
4. Build anytime using `cmake --build buld/<preset name>`
5. Output binary is at `./build/<preset name>/scheduler(.exe)`
