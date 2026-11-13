def solve(values):
    if not values:
        return []
    
    result = []
    current_length = 1
    
    for i in range(1, len(values)):
        if values[i] > values[i - 1]:
            current_length += 1
        else:
            result.append(current_length)
            current_length = 1
    
    result.append(current_length)
    return result
