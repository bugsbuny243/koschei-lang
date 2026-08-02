def main() -> None:
    success = False
    for attempt in range(1, 4):
        if attempt == 2:
            success = True
            break
        print(f"retry {attempt}")
    print(f"success: {str(success).lower()}")


main()
