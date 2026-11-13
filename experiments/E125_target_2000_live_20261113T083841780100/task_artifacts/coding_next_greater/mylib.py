def solve(values):
    n = len(values)
    result = [None] * n
    stack = []
    for i in range(n - 1, -1, -1):
        while stack and stack[-1] <= values[i]:
            stack.pop()
        if stack:
            result[i] = stack[-1]
        else:
            result[i] = None
        stack.append(values[i])
    return result
