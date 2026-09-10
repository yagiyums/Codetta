def process(values):
    total = 0
    for i in range(len(values)):
        x = values[i]
        if x > 3:
            total = total + x
    return total


values = [1, 2, 4, 6]
result = process(values)
