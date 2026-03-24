import baostock as bs
import pandas as pd
from datetime import datetime
import time
import sys
import os
import json
import re
from multiprocessing import Pool, cpu_count, freeze_support, set_start_method
from iFinDPY import *

iFinD = iFinD()
iFinD.login("shrhqy001","rrNGp35A")

if __name__ == "__main__":
    a = THS_RQ('688001.SH,688002.SH,688003.SH,688004.SH,688005.SH,688006.SH,688007.SH,688008.SH','latest')
    a.data.to_csv('thx2.txt', index=False)
