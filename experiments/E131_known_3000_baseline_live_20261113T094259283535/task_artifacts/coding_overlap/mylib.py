def occurrences(text, pattern):
    if not pattern:
        return 0
    count = 0
    start = 0
    while True:
        index = text.find(pattern, start)
        if index == -1:
            break
        count += 1
        start = index + 1
    return count
