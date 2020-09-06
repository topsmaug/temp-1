import os
import sys
import time


while True:
    cmd = 'curl sys.argv[1]'
    r = os.popen(cmd).readlines()
    print(r)
    time.sleep(1)
