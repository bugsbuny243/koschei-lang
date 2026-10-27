total = 0
i = 0
while i < 300000:
    total = total + i * i % 7
    i = i + 1
print(total)
