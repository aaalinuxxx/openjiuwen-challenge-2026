def rotate_right(values,k):
    if not values:return []
    k%=len(values)
    return values[-k:]+values[:-k] if k else values[:]
