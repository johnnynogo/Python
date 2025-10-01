import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import sys
from casadi import *
import os
import time
import do_mpc


# print(do_mpc.__version__) # First test to see if do_mpc is installed

# ===================================
# do_mpc data generation and handling
# ===================================

# Creating a sampling plan
sp = do_mpc.sampling.SamplingPlanner()
sp.set_param(overwrite = True)
sp.data_dir = './sampling_test/'

sp.set_sampling_var('alpha', np.random.randn)
sp.set_sampling_var('beta', lambda: np.random.randint(0,5))

# Generate sampling plan with arbitrary amount of cases
plan = sp.gen_sampling_plan(n_samples=10)

# Inspect plan with pandas, plan becomes list of dicts
pd.DataFrame(plan)

# Saving it to disc
sp.export('export_of_sampling_plan')

# Creating Sampler
sampler = do_mpc.sampling.Sampler(plan)
sampler.set_param(overwrite = True)

# Creating dummy sampling generating function f(a, b) = a * b
def sample_function(alpha, beta):
    time.sleep(0.1)
    return alpha * beta

sampler.set_sample_function(sample_function)

# Set directory for creates files and name
sampler.data_dir = './sampling_test/'
sampler.set_param(sample_name = 'dummy_sample')

# Create samples
sampler.sample_data()

ls = os.listdir('./sampling_test/')
ls.sort()
ls

# Process data in data handler class, firstly initiating class
dh = do_mpc.sampling.DataHandler(plan)

# Point where data is stored and how samples are called
dh.data_dir = './sampling_test/'
dh.set_param(sample_name = 'dummy_sample')

# Doing dummy post-processing
dh.set_post_processing('res_1', lambda x: x)
dh.set_post_processing('res_2', lambda x: x**2)

# Obtaining processed data
pd.DataFrame(dh[:3])
pd.DataFrame(dh.filter(input_filter = lambda alpha: alpha<0)) # retrieves alpha < 0
pd.DataFrame(dh.filter(output_filter = lambda res_2: res_2>10)) # filtering outputs

# Sampling closed loop-trajectories, need to import oscillating mass system
