# Project Documentation

This directory hosts semantic overviews and formal documents detailing the
entire project.

**Key Documents**:

- [Project Brief](./design/project-brief.md): initial requirements document
  provided by the client. Note that this only serves a very rough guide; not all
  details may make sense or will be followed through.
- [System Architectural Design](./design/system_component_design.md):
  semi-technical document describing the project structure from a systems
  engineering perspective.
- [API Schemas](./design/api-schemas.md): highly-tentative document summarizing
  the current inter-component APIs. This will evolve as the feature set expands.
- [Functional Design Specs](./design/functional_design.md): in-depth reference
  to how select features are implemented.
- [Coding Style Guide](./design/CODING_STYLE.md): high-level coding style guide
  for the entire project.

**Stats Forecasting Research**:

- [Data Analysis](./analysis/data_analysis.md): exploratory analysis of UK
  carbon intensity data across 5 regions.
- [Benchmark Report](./benchmarks/comparison_report.md): 18-model comparison
  (statistical, tree-based, deep learning, foundation models).
- [Experiment Report](./experiments/experiment_report.md): 5-stage iterative
  experiment from baseline to weather-enriched Direct-XGBoost (MAE 29.49).
- [Experiment Summary](./experiments/experiment_summary.md): comprehensive
  summary including per-region results and transformer analysis.

## Developer Information

Please amend existing and add new documentation as appropriate throughout
development.

Further information regarding each component (e.g. software stack & toolchain
information) resides in the readmes in their respective directories.
