import numpy as np
import matplotlib.pyplot as plt
# import gym
import sys

import torch
import math
from torch import nn
import torch.nn.functional as F
from torch import optim
from torch.distributions import Categorical, Normal, MultivariateNormal
from torch.autograd import grad
from rewardfunctions import *

import pdb

from scipy import linalg
# from networks import *
# from models import *

#device = 'cuda' if torch.cuda.is_available() else 'cpu'
device = 'cpu'

def count_parameters(model):
	return sum(p.numel() for p in model.parameters() if p.requires_grad)

def non_decreasing(L):
	return all(x>=y for x, y in zip(L, L[1:]))

def discount_rewards(list_of_rewards, discount, center=True, batch_wise=False):
	if isinstance(list_of_rewards, list) or isinstance(list_of_rewards, np.ndarray):
		list_of_rewards = np.asarray(list_of_rewards, dtype=np.float32)
		r = np.zeros_like(list_of_rewards)

		for i in range(len(list_of_rewards)):
			r = r + discount**i * np.pad(list_of_rewards,(0,i),'constant')[i:]

		if center:
			return torch.DoubleTensor((r - list_of_rewards.mean())/(list_of_rewards.std()+ 1e-5))
		else:
			return torch.DoubleTensor(r.copy())

	elif isinstance(list_of_rewards, torch.Tensor):
		r = torch.zeros_like(list_of_rewards)
		if batch_wise:
			lim_range = list_of_rewards.shape[1]
		else:
			lim_range = list_of_rewards.shape[0]

		for i in range(lim_range):
			r = r + discount**i * shift(list_of_rewards,i, dir='up')

		if center:
			return (r - torch.mean(list_of_rewards))/(torch.std(list_of_rewards) + 1e-5)
		else:
			return r
			
class StableNoise(object):
	def __init__(self, states_dim, salient_states_dim, param, init=1):
		self.states_dim = states_dim
		self.salient_states_dim = salient_states_dim
		self.extra_dim = self.states_dim - self.salient_states_dim
		self.param = param
		self.random_initial = 2*init*np.random.random(size = (self.extra_dim,)) - init #I THINK THIS NOISE SHOULD BE MORE AGGRESSIVE

	def get_obs(self, obs, t=0):
		if self.extra_dim == 0:
			return obs
		extra_obs = self.random_initial * self.param**t * np.random.random_sample()
		# split_idx = self.salient_states_dim + int(np.floor(self.extra_dim/3))
		new_obs = np.hstack([obs, extra_obs])
		return new_obs

#very stupidly written function, too lazy for now to make better 
def generate_data(env, states_dim, dataset, val_dataset, actor, train_starting_states, val_starting_states, max_actions,noise, epsilon, epsilon_decay, num_action_repeats, temp_data=False, discount=0.995, all_rewards=[], use_pixels=False, reset=True, start_state=None, start_noise=None):
	# dataset = ReplayMemory(1000000)
	noise_decay = 1.0 - epsilon_decay #0.99999
	if env.spec.id != 'lin-dyn-v0':
		salient_states_dim = env.observation_space.shape[0]
	else:
		salient_states_dim = 2

	stablenoise = StableNoise(states_dim, salient_states_dim, 0.992)

	for ep in range(train_starting_states):
		if reset or start_state is None:
			state = env.reset()
		else:
			state = start_state #have to find a way to set env to this state ... otherwise this is doing nothing
		# full_state = env.env.state_vector().copy()

		if env.spec.id != 'lin-dyn-v0' and reset:
			state = stablenoise.get_obs(state, 0)

		if use_pixels:
			obs = env.render(mode='pixels')
			observations = [preprocess(obs)]

		if reset or start_noise is None:
			noise.reset()
		else:
			noise = start_noise

		states = [state]
		actions = []
		rewards = []
		get_new_action = True
		for timestep in range(max_actions):
			if get_new_action:
				with torch.no_grad():
					action = actor.sample_action(torch.DoubleTensor(state)).detach().numpy()
					# action = actor.sample_action(torch.DoubleTensor(state[:salient_states_dim])).detach().numpy()#
					# action += noise()*max(0, epsilon) #try without noise
					# action = np.clip(action, -1., 1.)
					action = noise.get_action(action, timestep, multiplier=1.0)
					get_new_action = False
					action_counter = 1

			state_prime, reward, done, _ = env.step(action)
			#UNCOMMENT THESE FOR EXTRA DIMS AND REMOVE THE FULL_STATE NONSENSE!
			if env.spec.id != 'lin-dyn-v0':
				state_prime = stablenoise.get_obs(state_prime, timestep+1)
			if use_pixels:
				obs_prime = env.render(mode='pixels')
				observations.append(preprocess(obs_prime))
				
			if reward is not None: #WHY IS REWARD NONE sometimes?!
				actions.append(action)
				states.append(state_prime)
				rewards.append(reward)

				# dataset.push(full_state, state, state_prime, action, reward)
				if temp_data:
					dataset.temp_push(state, state_prime, action, reward)
				else:
					dataset.push(state, state_prime, action, reward)
			state = state_prime
			# full_state = env.env.state_vector().copy()

			get_new_action = True if action_counter == num_action_repeats else False
			action_counter += 1
		#returns = discount_rewards(rewards, discount, center=True, batch_wise=False)

		# for x, x_next, u, r, ret in zip(states[:-1], states[1:], actions, rewards, returns):
		# 	dataset.push(x, x_next, u, r, ret)
		# all_rewards.append(sum(rewards))
	# print('Average rewards on true dynamics: {:.3f}'.format(sum(all_rewards)/len(all_rewards)))

	# val_dataset = None
	if val_starting_states is not None:
		# val_dataset = ReplayMemory(100000)
		for ep in range(val_starting_states):
			state = env.reset()
			# full_state = env.env.state_vector().copy()
			if env.spec.id != 'lin-dyn-v0':
				state = stablenoise.get_obs(state, 0)
			states = [state]
			actions = []
			rewards = []

			for timestep in range(max_actions):
				with torch.no_grad():
					action = actor.sample_action(torch.DoubleTensor(state)).detach().numpy()
					# action = actor.sample_action(torch.DoubleTensor(state[:salient_states_dim])).detach().numpy()
					action = noise.get_action(action, timestep+1, multiplier=1.0)
					
				state_prime, reward, done, _ = env.step(action)
				if env.spec.id != 'lin-dyn-v0':
					state_prime = stablenoise.get_obs(state_prime, timestep+1)
				actions.append(action)
				states.append(state_prime)
				rewards.append(reward)
				# val_dataset.push(full_state, state, state_prime, action, reward)
				val_dataset.push(state, state_prime, action, reward)
				state = state_prime
				# full_state = env.env.state_vector().copy()

	return state, noise, epsilon


def lin_dyn(A, steps, policy, all_rewards, x=None, extra_dim=0, discount=0.9):
	#B = np.eye(2)
	#print linalg.eig(A)[0], np.abs(linalg.eig(A)[0])

	#This should be changed if it's actually used anywhere, to enable use with multiple x dimensions
	# if x is None:        
	# 	x = np.array([1.,0.])
	x = add_irrelevant_features(x, extra_dim=extra_dim, noise_level=0.4)
		
	EYE = np.eye(x.shape[0])

	x_list = [x]
	u_list = []
	r_list = []
	for m in range(steps):
		with torch.no_grad():
			u = policy.sample_action(torch.DoubleTensor(x).to(device)).cpu().numpy()
		
		u_list.append(u)

		r = -(np.dot(x.T, x) + np.dot(u.T,u))
		#r = -(np.dot(x[:-extra_dim].T, x[:-extra_dim]) + np.dot(u.T,u))
		if extra_dim > 0:
			x_next = np.asarray(A.dot(x[:-extra_dim])) #in case only one dimension is relevant
		else:
			x_next = A.dot(x)

		x_next = add_irrelevant_features(x_next, extra_dim=extra_dim, noise_level=0.4)
		x_next = x_next + u

		x_list.append(x_next)
		r_list.append(r)
		x = x_next
	
	x_list = np.array(x_list)
	u_list = np.array(u_list)
	r_list = np.array(r_list)

	x_curr = x_list[:-1,:]
	x_next = x_list[1:,:]
#    r = x_curr[:,0]
	# Quadratic reward

	#change reward:
	#r_list = -np.clip(x_curr[:,0]**2, 0., 1.0)

	all_rewards.append(sum(r_list))

	##WHY DIDN"T WORK WITH DISCOUNT + 0????? center was set to true ... 
	#returns1 = discount_rewards(r_list, discount, center=True)
	#returns1 = torch.from_numpy(r_list)

	#returns2 = discount_rewards(r2, discount, center=True)

#    r = float32(x_curr[:,0] > 0.1)
	
#    return x_list, r
	return x_curr, x_next, u_list, returns1, r_list


def add_irrelevant_features(x, extra_dim, noise_level = 0.4):
#    x_irrel= np.random.random((x.shape[0], extra_dim))
	if isinstance(x, np.ndarray):
		x_irrel= noise_level*np.random.randn(1, extra_dim).reshape(-1,)
	#    x_irrel_next = x_irrel**2 + 1.0
	#    x_irrel_next = x_irrel**2
	#    x_irrel_next = 0.1*np.random.random((x.shape[0], extra_dim))
	#	x_irrel_next = noise_level*np.random.randn(x.shape[0], extra_dim)
	#    x_irrel_next = x_irrel**2 + noise_level*np.random.randn(x.shape[0], extra_dim)    
	#    x_irrel_next = x_irrel**2 + np.random.random((x.shape[0], extra_dim))
		return np.hstack([x, x_irrel])#, np.hstack([x_next, x_irrel_next])

	elif isinstance(x, torch.Tensor):
		x_irrel= noise_level*torch.randn(x.shape[0],x.shape[1],extra_dim).double().to(device)
		#x_irrel_next = noise_level*torch.randn(x.shape[0],x.shape[1],extra_dim).double()
		
		return torch.cat((x, x_irrel),2)#, torch.cat((x_next, x_irrel_next),2)


def convert_one_hot(a, dim):
	if dim == 2: #binary value, no need to do one-hot encoding
		return a

	if a.shape:
		retval = torch.zeros(list(a.shape)+[dim])
		retval[list(np.indices(retval.shape[:-1]))+[a]] = 1
	else: #single value tensor
		retval = torch.zeros(dim)
		retval[int(a)] = 1
	return retval



def roll_1(x, n):  
	return torch.cat((x[:, -n:], x[:, :-n]), dim=1)



def shift(x, step, dir='up'):
	#up works, not tested down
	if step == 0:
		return x

	if len(x.shape) == 3: #batch_wise
		if dir=='down':
			return torch.cat((torch.zeros((x.shape[0], step, x.shape[2])).double().to(device),x),dim=1)[:,:-step]
		elif dir=='up':
			return torch.cat((x,torch.zeros((x.shape[0], step, x.shape[2])).double().to(device)),dim=1)[:,step:]

	elif len(x.shape) == 2: 
		if dir=='down':
				return torch.cat((torch.zeros((step, x.shape[1])).double().to(device),x),dim=0)[:-step]
		elif dir=='up':
			return torch.cat((x,torch.zeros((step, x.shape[1])).double().to(device)),dim=0)[step:]

	else:
		raise NotImplementedError('shape {shape_x} of input not corrent or implemented'.format(shape_x=x.shape))



def roll_left(x, n):  
	#return torch.cat((x[-n:], x[:-n]))
	return torch.cat((x[n:], x[:n]))


def calc_actual_state_values(target_critic, rewards, states, actions, discount):
	R = []
	rewards.reverse()

	# # If we happen to end the set on a terminal state, set next return to zero
	# if dones[-1] == True: next_return = 0
	    
	# If not terminal state, bootstrap v(s) using our critic
	# TODO: don't need to estimate again, just take from last value of v(s) estimates
	# s = torch.from_numpy(states[-1]).double().unsqueeze(0)
	# a = torch.from_numpy(actions[-1]).double().unsqueeze(0)
	s= states
	a = actions
	next_return = target_critic(torch.cat((s,a),dim=1)).data[0][0]

	# Backup from last state to calculate "true" returns for each state in the set
	R.append(next_return)
	# dones.reverse()
	for r in range(1, len(rewards)):
		# if not dones[r]: this_return = rewards[r] + next_return * discount
		this_return = torch.from_numpy(rewards[r]) + next_return * discount
		# else: this_return = 0
		R.append(this_return)
		next_return = this_return

	R.reverse()
	state_values_true = torch.DoubleTensor(R).unsqueeze(1)

	return state_values_true


def compute_returns(self, obs, action, reward, next_obs, done):  # pylint: disable=unused-argument
	with torch.no_grad():
		values, dist = self.ac_net(obs)
		if not done[-1]:
			next_value, _ = self.ac_net(next_obs[-1:])
			values = torch.cat([values, next_value], dim=0)
		else:
			values = torch.cat([values, values.new_tensor(np.zeros((1, 1)))], dim=0)

		returns = reward.new_tensor(np.zeros((len(reward), 1)))
		gae = 0.0
		for step in reversed(range(len(reward))):
			delta = reward[step] + self.gamma * values[step + 1] - values[step]
			gae = delta + self.gamma * self.lmbda * gae
			returns[step] = gae + values[step]

		values = values[:-1]  # remove the added step to compute returns

	return returns, log_probs, values


def get_selected_log_probabilities(policy_estimator, states_tensor, actions_tensor):#, batch_actions):

	action_probs = policy_estimator.get_action_probs(states_tensor)
	if not policy_estimator.continuous:
		c = Categorical(action_probs[0])
		selected_log_probs = c.log_prob(actions_tensor)
		
		# log_probs = torch.log(torch.clamp(action_probs[0],min=1e-5))
		# if ((log_probs < -100).any()):
		# 	pdb.set_trace()
		# selected_log_probs = log_probs.view(-1,2).gather(1, actions_tensor.view(-1,1))
		# selected_log_probs = torch.index_select(log_probs, 1, actions_tensor)[range(len(actions_tensor)), range(len(actions_tensor))]
	else:
		n = Normal(*action_probs)
		selected_log_probs = n.log_prob(actions_tensor)
		#entropies = n.entropy()

	return selected_log_probs#, entropies


#################### IGNORE BELOW ##############################

##doesn't work so well now, next_step_state_val[:,:-4] this part is probably wrong
def mle_multistep_loss(P_hat, policy, val_states_next_tensor, state_actions_val, n_actions, max_actions, R_range, continuous_actionspace=False, device='cpu'):

	squared_errors_val = torch.zeros_like(val_states_next_tensor)

	horizon = R_range - 1
	step_state_val = state_actions_val.to(device)[:,:-horizon]

	with torch.no_grad():
		for step in range(max_actions*2-1):
			next_step_state_val = P_hat(step_state_val)

			if step==0:
				err1_step = torch.mean((val_states_next_tensor[:,:-horizon] - next_step_state_val)**2)
			elif step == 5:
				err5_step = torch.mean((val_states_next_tensor[:,5:5+max_actions*2-horizon] - next_step_state_val[:,:-4])**2)
			elif step == 10:
				err10_step = torch.mean((val_states_next_tensor[:,10:10+max_actions*2-horizon] - next_step_state_val[:,:-9])**2)
			elif step == 18:
				err20_step = torch.mean((val_states_next_tensor[:,18:18+max_actions*2-horizon] - next_step_state_val[:,:-17])**2)

			#squared_errors_val += F.pad(input=(val_states_next_tensor[:,step:,:] - next_step_state_val)**2, pad=(0,0,step,0,0,0), mode='constant', value=0)
			shortened_val = next_step_state_val
			action_probs_val = policy(torch.DoubleTensor(shortened_val))
			
			if not continuous_actionspace:
				c_val = Categorical(action_probs_val[0])
				a_val = c_val.sample().type(torch.DoubleTensor).to(device)
				step_state_val = torch.cat((shortened_val, convert_one_hot(a_val, n_actions).unsqueeze(2)),dim=2)
			else:
				c_val = Normal(*action_probs_val)
				a_val = torch.clamp(c_val.rsample(), min=-2.0, max=2.0)
				step_state_val = torch.cat((shortened_val, a_val),dim=2)

	# if squared_errors_val.shape < 2:
	# 	squared_errors_val.unsqueeze(0)
	
	# err_1step = torch.mean(squared_errors_val[:,1])
	# err_5step = torch.mean(squared_errors_val[:,5])
	# err_10step = torch.mean(squared_errors_val[:,10])
	# err_10step = torch.mean(squared_errors_val[:,19])

	# try:
	# 	err_50step = torch.mean(squared_errors_val[:,50])
	# 	err_100step = torch.mean(squared_errors_val[:,100])
	# except:
	# 	err_50step = 0
	# 	err_100step = torch.mean(squared_errors_val[:,-1])

	print("Multistep error values:", err1_step, err5_step, err10_step, err20_step, "\n")	

	return err1_step


def compute_normalization(data):
    """
    Write a function to take in a dataset and compute the means, and stds.
    Return 6 elements: mean of s_t, std of s_t, mean of (s_t+1 - s_t), std of (s_t+1 - s_t), mean of actions, std of actions
    """

    # flatten dataset across all paths
    observations = np.stack([item.state for item in data.memory])
    next_observations = np.stack([item.next_state for item in data.memory])
    actions = np.stack([item.action for item in data.memory])
    
    mean_obs = torch.tensor(np.mean(observations, axis=0)).unsqueeze(0)
    std_obs = torch.tensor(np.std(observations, axis=0)).unsqueeze(0)
    
    mean_deltas =  torch.tensor(np.mean(next_observations - observations, axis=0)).unsqueeze(0)
    std_deltas = torch.tensor(np.std(next_observations - observations, axis=0)).unsqueeze(0)
    
    mean_actions = torch.tensor(np.mean(actions, axis=0)).unsqueeze(0)
    std_actions = torch.tensor(np.std(actions, axis=0)).unsqueeze(0)

    return mean_obs, std_obs, mean_deltas, std_deltas, mean_actions, std_actions


# def paml_validation_loss(env, P_hat, policy, val_states_prev_tensor, val_states_next_tensor, actions_tensor_val, rewards_tensor_val, R_range, val_size, n_actions, max_actions, continuous_actionspace=False, device='cpu'):

# 	state_actions_val = torch.cat((val_states_prev_tensor, actions_tensor_val),dim=2)

# 	policy.zero_grad()
# 	multiplier = torch.arange(max_actions,0,-1).repeat(val_size,1).unsqueeze(2).type(torch.DoubleTensor).to(device)
# 	true_log_probs_t = torch.sum(
# 						get_selected_log_probabilities(
# 							policy, 
# 							val_states_prev_tensor, 
# 							actions_tensor_val, 
# 							range(actions_tensor_val.shape[0])
# 							) * rewards_tensor_val #* multiplier
# 						, dim=1)

# 	true_log_probs = torch.mean(true_log_probs_t, dim=0)
# 	true_pe_grads = grad(true_log_probs, policy.parameters(), create_graph=True)


# 	step_state_action_val = state_actions_val.to(device)
# 	k_step_log_probs = torch.zeros((R_range, val_size, n_actions))

# 	policy.zero_grad()
# 	for step in range(R_range):
# 		with torch.no_grad():
# 			next_step_state = P_hat(step_state_action_val)
# 		#print('states_mean:', torch.mean(next_step_state))
# 		shortened = next_step_state[:,:-1,:]

# 		with torch.no_grad():
# 			action_probs = policy(torch.DoubleTensor(shortened))
			
# 			if not continuous_actionspace:
# 				c = Categorical(action_probs)
# 				actions_t_l = c.sample() 
# 				step_state_action_val = torch.cat((shortened,convert_one_hot(actions_t_l, n_actions)),dim=2)
# 			else:
# 				c = Normal(*action_probs)
# 				actions_t_l = torch.clamp(c.rsample(), min=-2.,max=2.)
# 				step_state_action_val = torch.cat((shortened, actions_t_l),dim=2)


# 		model_rewards_t = get_reward_fn(env, shortened, actions_t_l)
# 		model_log_probs = torch.sum(
# 						get_selected_log_probabilities(
# 								policy, 
# 								shortened,
# 								actions_t_l, range(actions_t_l.shape[0])) * 
# 								model_rewards_t
# 							, dim=1)

# 		#pdb.set_trace()
# 		k_step_log_probs[step] = model_log_probs#.squeeze()

# 	model_log_probs = torch.mean(torch.sum(k_step_log_probs, dim=0))

# 	model_pe_grads = grad(model_log_probs, policy.parameters(), create_graph=True)
# 	#total_log_probs.backward(retain_graph=True)
# 	#model_pe_grads = [x.grad for x in pe.parameters()]

# 	model_loss_val = 0
# 	for i in range(len(true_pe_grads)):
# 		model_loss_val += torch.sqrt(torch.sum((model_pe_grads[i] - true_pe_grads[i])**2))

# 	print('PAML validation loss:', model_loss_val.detach().data.cpu())

# 	return model_loss_val.detach().data



# def collect_data(env, policy, episodes, n_actions, n_states, R_range, max_actions, continuous_actionspace=False, device='cpu'):
# 	states_prev_list = []
# 	states_next_list = []
# 	all_actions_list = []
# 	all_rewards_list = []

# 	for ep in range(episodes):
# 		s = env.reset()
# 		done = False
# 		states_list = [s]
# 		actions_list = []
# 		rewards_list = []
# 		while len(actions_list) < max_actions:
# 			with torch.no_grad():
# 				if device == 'cuda':
# 					action_probs = policy(torch.cuda.DoubleTensor(s))
# 				else:
# 					action_probs = policy(torch.DoubleTensor(s))

# 				if not continuous_actionspace:
# 					c = Categorical(action_probs[0])
# 					a = c.sample() 
# 				else:
# 					c = Normal(*action_probs)
# 					a = c.rsample()

# 				s_prime, r, done, _ = env.step(a.cpu().numpy() - 1)
# 				states_list.append(s_prime)
# 				rewards_list.append(r)

# 				if not continuous_actionspace:
# 					actions_list.append(convert_one_hot(a, n_actions))
# 				else:
# 					actions_list.append(a)

# 				s = s_prime

# 		states_prev_list.extend(states_list[:-R_range-1])
# 		states_next_list.extend(states_list[R_range+1:])
# 		all_actions_list.extend(actions_list)
# 		all_rewards_list.extend(rewards_list)

# 	states_prev_tensor = torch.DoubleTensor(states_prev_list).to(device).view(episodes, -1, n_states)
# 	states_next_tensor = torch.DoubleTensor(states_next_list).to(device).view(episodes, -1, n_states)
# 	actions_tensor = torch.stack(all_actions_list).type(torch.DoubleTensor).to(device).view(episodes, -1, n_actions)
# 	rewards_tensor = torch.DoubleTensor(all_rewards_list).to(device).view(episodes, -1, n_actions)

# 	return states_prev_tensor, states_next_tensor, actions_tensor, rewards_tensor

