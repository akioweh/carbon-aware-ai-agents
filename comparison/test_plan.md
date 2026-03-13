Let's group by:
- different models, same system
- same model, different system
- the biggest saving when using ours
- the smallest savings when using ours

Each test looks like this:
- we iterate over workload to compute: [0.5, 1, 1.5, 2, 4, 8, 16]
- then we also iterate over full power, of half power
- then for each config we calc the time it will take
- we run both our scheduler, and their - comparing the results.
- the X axis is workload to compute, and Y axis is amount of emitted carbon
