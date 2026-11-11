from a_normalize import normalize

def lookup(mapping, query):
    normalized_query = normalize(query)
    for key in mapping:
        if normalize(key) == normalized_query:
            return mapping[key]
    return None
