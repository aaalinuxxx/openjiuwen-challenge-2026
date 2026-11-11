from a_units import METRES_PER_UNIT

def convert(value, source, target):
    return value * METRES_PER_UNIT[target] / METRES_PER_UNIT[source]
