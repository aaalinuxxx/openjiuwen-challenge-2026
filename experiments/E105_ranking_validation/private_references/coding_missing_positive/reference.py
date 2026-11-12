def first_missing_positive(values):
    seen=set(values);n=1
    while n in seen:n+=1
    return n
