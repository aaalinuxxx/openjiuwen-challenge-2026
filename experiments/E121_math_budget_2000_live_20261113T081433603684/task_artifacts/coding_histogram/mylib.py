def solve(values):
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return sorted(counts.items())
