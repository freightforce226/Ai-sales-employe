import sys
try:
    import bleach
    print("bleach is installed")
except ImportError:
    print("bleach is NOT installed")

try:
    import nh3
    print("nh3 is installed")
except ImportError:
    print("nh3 is NOT installed")
