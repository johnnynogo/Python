import numpy as np
import matplotlib.pyplot as plt
import do_mpc
from casadi import vertcat, sqrt

# Placeholder constants
A = 2
k = 3
u_max = 10
h_max = 8
w_true = 3
h_ref = 5

# MPC constants
dt = 0.2
n_horizon = 40
Q_h = 40 # weight on height tracking error
R_u = 0.2 # weight on input effort

# ========================
# Building nonlinear model
# ========================
def build_model():
    model_type = 'continuous'
    model = do_mpc.model.Model(model_type)

    h = model.set_variable(var_type='_x', var_name='h') # states
    u = model.set_variable(var_type='_u', var_name='u') # input
    w = model.set_variable(var_type='_p', var_name='w') # parameter (leakage)

    dh = (1 / A) * (u - k * sqrt(h +1e-9) - w)
    model.set_rhs('h', dh)

    model.setup()
    return model

model = build_model()

# ========================
# Configure MPC Controller
# ========================
mpc = do_mpc.controller.MPC(model)

setup_mpc = {
    'n_horizon': n_horizon,
    't_step': dt,
    'store_full_solution': True
}
mpc.set_param(**setup_mpc) # mpc(n_horizon, t_step, (other optional params))

h = model.x['h'] # stage cost
u = model.u['u'] # terminal cost
lterm = Q_h * (h - h_ref)**2 + R_u * u**2
mterm = Q_h * (h - h_ref)**2

mpc.set_objective(mterm=mterm, lterm=lterm)
mpc.set_rterm(u=R_u)

# Input bounds
mpc.bounds['lower', '_u', 'u'] = 0
mpc.bounds['upper', '_u', 'u'] = u_max

# State bounds

mpc.bounds['lower', '_x', 'h'] = 0
mpc.bounds['upper', '_x', 'h'] = h_max

mpc.set_uncertainty_values(w=np.array([w_true])) # declaring parameters that vary over horizon

mpc.setup()

# ======================
# Simple State Estimator
# ======================
est = do_mpc.estimator.StateFeedback(model)

# =======================
# Simulator (truth model)
# =======================
simulator = do_mpc.simulator.Simulator(model)
simulator.set_param(t_step=dt)

# Provide parameters to the simulator
p_template = simulator.get_p_template()
def p_fun(t_now):
    p_template['w'] = w_true
    return p_template
simulator.set_p_fun(p_fun)

simulator.setup()

# ==================
# Initial Conditions
# ==================
h0 = 1
x0 = mpc.x0
x0['h'] = h0
mpc.x0 = x0
simulator.x0 = x0
est.x0 = x0

mpc.set_initial_guess()

# ======================
# Closed-loop Simulation
# ======================
T_sim = 40
N_sim = int(T_sim/dt)

h_hist = [float(h0)]
u_hist = []
t_hist = [0]

x_est = mpc.x0

for k_step in range(N_sim):
    t_now = (k_step + 1) * dt
    # mpc.set_parameters(w=w_true)
    # u0 = mpc.make_step(est.x0)
    u0 = mpc.make_step(x_est)
    y_next = simulator.make_step(u0)
    # est_measurement = y_next
    # est.x0 = est_measurement
    h_meas = float(np.array(y_next).squeeze())
    # x_est = est.make_step(y_next)
    x_est['h'] = h_meas

    # h_hist.append(float(x_est['h']))
    h_hist.append(h_meas)
    u_hist.append(float(u0))
    t_hist.append(t_now)

# =====
# Plots
# =====
plt.figure()
plt.plot(t_hist, h_hist, label='h (level)')
plt.axhline(h_ref, linestyle='--', label='h_ref')
plt.xlabel('time [s]')
plt.ylabel('level h [m]')
plt.legend()
plt.title('Tank level')

plt.figure()
plt.step(t_hist[:-1], u_hist, where='post', label='u (inflow)')
plt.xlabel('time [s]')
plt.ylabel('u')
plt.legend()
plt.title('Control input')

plt.show()


# Now consider how MPC can be used for our solar race. Think abstract and about hard problems and how to solve them.
# -? How often do we want to simulate? || How do we want to simulate?
# --?? How should we simulate - often and spend little time without crunching many numbers or spend a lot of time doing  'careful' simulation crunching heavy numbers
# ---- The way I want to simulate now is by letting x0 be start, run simulation that tells how we should drive first lap. Drive one lap, retrieve information from car (SoC, energy consumption, weather data, etc.), run simulation again.
# ---- Will a strategy be to simulate if we see values that does not correspond to the values that were simulated, if so what is threshhold for this.
# -? Are we able to continually retrieve data from car (SoC, energy consumption, etc.) so that when we are ready to run a simulation we can press run.
# ---- Canbus
# -? Do we do simulations at night the same as when there is (potentially) a lot of sun?
# -? 
