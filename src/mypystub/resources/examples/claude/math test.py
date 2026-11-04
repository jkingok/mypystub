# Arithmetic, loops, and functions, standard library only.
def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0:
            return False
    return True


primes = [n for n in range(1, 51) if is_prime(n)]
print("Primes up to 50:")
print(primes)
print("Count:", len(primes))
