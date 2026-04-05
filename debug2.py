import sys
original = sys.path.copy()
import quickstart
sys.path[:] = original

print("sys.path:", sys.path)
try:
    import kernel.organizations
    print("Success")
except Exception as e:
    print("Failed:", repr(e))
