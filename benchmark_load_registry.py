import time
import os
from kernel.agent_registry import load_registry

def benchmark():
    start = time.perf_counter()
    for _ in range(1000):
        load_registry()
    end = time.perf_counter()
    print(f"Elapsed time for 1000 calls: {end - start:.5f} seconds")

if __name__ == "__main__":
    benchmark()
