parts = []
i = 0
while i < 3000:
    parts = parts + [f"item{i}"]
    i += 1
joined = ",".join(parts)
back = joined.split(",")
print(len(joined), len(back))
