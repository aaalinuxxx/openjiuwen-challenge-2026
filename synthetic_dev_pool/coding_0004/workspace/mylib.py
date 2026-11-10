def reverse_words(s):
    return ' '.join(reversed(s.split()))

def total(xs):
    return sum(xs)

def maximum(xs):
    return max(xs) if xs else 0

def average(xs):
    # BUG: division by len-1
    return sum(xs) / (len(xs) - 1) if len(xs) > 1 else xs[0]

def count_even(xs):
    # BUG: counts odd instead
    return sum(1 for x in xs if x % 2 == 1)
