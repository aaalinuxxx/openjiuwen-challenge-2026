from a_settings import threshold

def keep(values):
    return [x for x in values if x >= threshold()]
