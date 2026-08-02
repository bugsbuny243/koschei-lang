raw = "port=8080\nworkers=4"
config = {key: int(value) for key, value in (line.split("=") for line in raw.splitlines())}
print(config["port"])
print(config["workers"])
