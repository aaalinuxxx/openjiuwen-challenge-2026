def transpose(matrix):
    if not matrix:
        return []
    return [list(row) for row in zip(*matrix)]
