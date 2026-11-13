def solve(values):
    result = []
    running_sum = 0
    for v in values:
        running_sum += v
        result.append(running_sum)
    return result
