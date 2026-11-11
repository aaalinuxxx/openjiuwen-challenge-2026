def occurrences(text, pattern):
    if not pattern:
        return 0
    count = 0
    start = 0
    while True:
        pos = text.find(pattern, start)
        if pos == -1:
            break
        count += 1
        start = pos + 1
    return count
