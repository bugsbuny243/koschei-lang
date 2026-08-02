from collections import defaultdict

purchases = [("Ada", 5), ("Grace", 7), ("Ada", 3)]
totals = defaultdict(int)
for customer, amount in purchases:
    totals[customer] += amount
print(totals["Ada"])
print(totals["Grace"])
