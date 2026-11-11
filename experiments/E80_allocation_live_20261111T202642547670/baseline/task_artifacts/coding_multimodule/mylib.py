from a_settings import threshold
def keep(values):
    return [v for v in values if v >= threshold()]
