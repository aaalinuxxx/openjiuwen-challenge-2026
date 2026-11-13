def rotate_right(values, k):
    if not values:
        return []
    n = len(values)
    k = k % n
    if k == 0:
        return values[:]
    return values[-k:] + values[:-k]
