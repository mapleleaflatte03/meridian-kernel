import time
import os
import json
from kernel.agent_registry import get_agents_by_economy_key, load_registry, save_registry

def setup():
    # create a large registry
    data = load_registry()
    data['agents'] = {}
    for i in range(10000):
        agent_id = f'agent_{i}'
        data['agents'][agent_id] = {
            'id': agent_id,
            'org_id': f'org_{i % 10}',
            'economy_key': f'key_{i % 100}',
        }
    save_registry(data)

def measure():
    start = time.time()
    for _ in range(100):
        get_agents_by_economy_key('key_50', org_id='org_5')
    end = time.time()
    print(f"Time taken: {end - start:.4f} seconds")

if __name__ == '__main__':
    setup()
    measure()
