from a_normalize import normalize

def lookup(mapping, query):
    for key, value in mapping.items():
        if normalize(key) == normalize(query):
            return value
    return None
