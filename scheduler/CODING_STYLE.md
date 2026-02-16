# Scheduler Component Coding Style

This document defines the coding standards and conventions for the C++ scheduler
component. Adherence to these styles ensures consistency, readability, and
maintainability across the codebase.

## Language Standards

- **C++ Version:** C++23.
- **Goal:** Maximally leverage the newest language and STL features (up to
  C++23).

## Core Principles

- **Modularity:** Every piece of code should have a single main responsibility.
  Avoid mixing concerns and tight logic coupling.
- **Layered Architecture:** Maintain strict boundaries between the HTTP layer,
  domain logic, and persistence layer. Use distinct types (DTOs, Domain Types,
  ORM Models) at each boundary.
- **Concurrency & Parallelism:**
  - Use `scheduler::coro::when_all` for concurrent asynchronous tasks (e.g.,
    I/O, API calls).
  - Parallelize computationally expensive algorithms using `std::async` or
    `std::for_each` with execution policies.
  - Design solutions with scalability and performance in mind.

## Code Conventions

### Variable Initialization

- **Always Initialize:** If you are declaring a stack variable without
  initialization (e.g. `int x;`), consider if you really need to do this.
- **Prefer `auto`:** Use the assignment format with `auto` for almost viable
  initializations:
  - **Class Types:** `auto var = MyClass();` or `auto var = MyClass{};`.
  - **Aggregate Types:** always define aggregates with default-initialized
    members; initialize aggregates with brace initialization.
  - **Primitive Types:** Do not explicitly write the type when it's obvious or
    can be inferred. Use literal suffixes where necessary:
    - `auto x = 1;` (int)
    - `auto y = 1.;` (double) no digits after `.` if value is whole
    - `auto z = 1ULL;` (unsigned long long)
    - `auto s = 1UZ;` (size_t)
    - `auto sv = "asdf"sv;` (std::string_view)

### Control Flow

- **Braces:** Do not use braces for single-statement `if`, `else`, `for`, or
  `while` blocks.
  - **Exception:** In multi-statement `if-else` chains, if any branch requires
    braces, use braces for all branches in that chain to maintain consistency.

### Functions

- **Trailing Return Types:** User trailing return types for all function
  declarations.

  ```cpp
  auto my_function(int arg) -> int;
  ```

### Casts

- **C++ Style Casts:** Always use C++ style casts (`static_cast`,
  `reinterpret_cast`, etc.). Never use C-style casts `(type)value`.

### Loops and Algorithms

- **Modern STL Algorithms:** Always prefer modern algorithms and STL library
  functions over manual C-style loops.
- **Ranges and Views:** Use `std::views` for iteration where possible:
  - `for (const auto i : std::views::iota(0, n))` for simple incrementing loops.
  - `for (const auto &[index, value] : std::views::enumerate(container))` for
    indexed iteration.
- **Decrementing Loops:** For loops that decrement from `N-1` to `0`, use the
  following pattern:

  ```cpp
  for (auto i = N; i--;) {
      // i goes from N-1 down to 0
  }
  ```

### Const Correctness

- **Everything Const:** Mark everything `const` if it can be `const`. This
  includes variables, function parameters, and member functions.

### Include Guards

All header files must use dual include guards: a macro-based guard and
`#pragma once`.

- **Macro Format:** `SCHEDULER_<FILE_NAME>_<EXTENSION>`
- **Placement:** `#pragma once` must be placed right under the `#define`.
- **Endif Comment:** The `#endif` must include a comment with the macro name.

Example, if file is `MyHeader.hpp`:

```cpp
#ifndef SCHEDULER_MY_HEADER_HPP
#define SCHEDULER_MY_HEADER_HPP
#pragma once

// ... code ...

#endif // SCHEDULER_MY_HEADER_HPP
```

### Data Structure Design

- Prefer aggregate types for structural data.
- Other than API structures, structure data for efficiency based on their usage.

### Formatting

- **Tool:** `clang-format` (config: `.clang-format`)
- **Style:** Based on LLVM
- **Indentation:** 4 spaces (no tabs)
- **Line Length:** Generally preferred to keep lines readable, managed by
  `clang-format`.

### Linting

- **Tool:** `clang-tidy` (config: `.clang-tidy`)
- **Proactive Resolution:** Pay close attention to and resolve all `clang-tidy`
  diagnostics, especially those regarding code style and modernization.
- **Integrations:** `clangd` provides real-time diagnostics in most modern
  editors.

### Naming & Structure

- **Namespace:** Application code live under the `scheduler` namespace (or a
  relevant sub-namespace e.g., `scheduler::utils`, `scheduler::coro`).
- **Filenames:** Match the class name or primary functionality (e.g.,
  `Scheduler.hpp`, `Utils.hpp`).
- **DTOs:** Place data transfer aggregate types in `src/structs/`.

## Documentation

- **Inline Comments:** Focus on _why_ something is done rather than _what_.
- **Doxygen:** Use Doxygen-style comments for classes and public functions to
- Extended discussion should go in the project documentation rather than in code
  comments.
- Always check documentation for accuracy and update it when making changes to
  the codebase.
