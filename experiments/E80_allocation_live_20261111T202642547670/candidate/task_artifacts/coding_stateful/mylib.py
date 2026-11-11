class Counter:
    def __init__(self):
        self.value = 0

    def next(self):
        self.value += 1
        return self.value
