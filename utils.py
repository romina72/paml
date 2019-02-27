import numpy as np
import matplotlib.pyplot as plt
import gym
import sys

import torch
import math
from torch import nn
from torch import optim
from torch.distributions import Categorical, Normal, MultivariateNormal
from torch.autograd import grad
from rewardfunctions import *

import pdb

from scipy import linalg


#device = 'cuda' if torch.cuda.is_available() else 'cpu'

def discount_rewards(list_of_rewards, discount, center=True, batch_wise=False):
	# r_tensor = torch.DoubleTensor(list_of_rewards)
	# all_discounts = [discount**i for i in range(r_tensor.shape[0])]
	# all_discounts.reverse()
	# G_list = r_tensor * torch.DoubleTensor(all_discounts)
	#return G_list - G_list.mean()
	#list_of_rewards = list_of_rewards.numpy()

	if isinstance(list_of_rewards, list) or isinstance(list_of_rewards, np.ndarray):

		# if batch_wise:
		# 	#this is wrong
		# 	pdb.set_trace()
			
		# 	r = np.empty_like(list_of_rewards)
		# 	for i in range(list_of_rewards.shape[1]):
		# 		r[:,i] = discount**i * list_of_rewards[:,i]

		# 	# Reverse the array direction for cumsum and then
		# 	# revert back to the original order
		# 	r = r[:,::-1].cumsum(axis=1)[:,::-1]
		# 	if center:
		# 		return torch.DoubleTensor((r - r.mean(axis=1))/(r.std(axis=1)+ 1e-5))
		# 	else:
		# 		return torch.DoubleTensor(r.copy())
		# else:
		r = np.zeros_like(list_of_rewards)

		for i in range(len(list_of_rewards)):
			r = r + discount**i * np.pad(list_of_rewards,(0,i),'constant')[i:]

		# r = np.array([discount**i * list_of_rewards[i] 
		# 	for i in range(len(list_of_rewards))])
		# # Reverse the array direction for cumsum and then
		# # revert back to the original order
		# r = r[::-1].cumsum()[::-1]
		if center:
			return torch.DoubleTensor((r - r.mean())/(r.std()+ 1e-5))
		else:
			return torch.DoubleTensor(r.copy())

	elif isinstance(list_of_rewards, torch.Tensor):

		r = torch.zeros_like(list_of_rewards)
		if batch_wise:
			lim_range = list_of_rewards.shape[1]
			dim_mean = 1 
		else:
			lim_range = list_of_rewards.shape[0]
			dim_mean = 0

		for i in range(lim_range):
				r = r + discount**i * shift(list_of_rewards,i,dir='up')

		if center:
			return (r - torch.mean(r, dim=dim_mean))/(torch.std(r,dim=dim_mean) + 1e-5)
		else:
			return r

		# if batch_wise:
			
		# 	r = torch.zeros_like(list_of_rewards)
		# 	for i in range(list_of_rewards.shape[1]):
		# 		r = r + discount**i * shift(list_of_rewards,i,dir='up')

		# 	# #this part not debugged!!!! .... looks fine
		# 	# r = torch.zeros_like(list_of_rewards)

		# 	# for i in range(list_of_rewards.shape[1]):
		# 	# 	r[:,i] = discount**i * list_of_rewards[:,i]

		# 	# discounted = torch.zeros_like(list_of_rewards)
			
		# 	# for i in range(r.shape[1]):
		# 	# 	discounted[:,i] = torch.sum(r[:,i:], dim=1)
		
		# 	#seems like pytorch std is more correct? Bessel correction?
		# 	if center:
		# 		return (r - torch.mean(r, dim=1))/(torch.std(r,dim=1) + 1e-5)#_batch
		# 	else:
		# 		return r

		# else:
		# 	#something wrong here
		# 	r = torch.zeros_like(list_of_rewards)
		# 	for i in range(list_of_rewards.shape[0]):
		# 		r = r + discount**i * shift(list_of_rewards,i,dir='up')

		# 	# pdb.set_trace()
		# 	# #not batchwise!!! only meant to be used with a single episode
		# 	# r = torch.zeros_like(list_of_rewards)
		# 	# for i in range(list_of_rewards.shape[0]):
		# 	# 	r[i] = discount**i * list_of_rewards[i]

		# 	# discounted = torch.zeros_like(list_of_rewards)
			
		# 	# for i in range(r.shape[0]):
		# 	# 	discounted[i] = torch.sum(r[i:], dim=0)
			
		# 	#seems like pytorch std is more correct? Bessel correction?
		# 	if center:
		# 		return (r - torch.mean(r))/(torch.std(r) + 1e-5)#_batch
		# 	else:
		# 		return r


def lin_dyn(steps, policy, all_rewards, x=None, discount=0.9):
	
	A = np.array([[0.9, 0.4], [-0.4, 0.9]])
	#B = np.eye(2)
#    print linalg.eig(A)[0], np.abs(linalg.eig(A)[0])
	if x is None:        
		x = np.array([1.,0.])
		
	EYE = np.eye(x.shape[0])

	x_list = [x]
	u_list = []
	r_list = []
	for m in range(steps):
		params = policy(torch.DoubleTensor(x))
		params = (params[0].detach(), params[1].detach())
		c = Normal(*params)
		u = torch.clamp(c.rsample(), min=-10., max=10.).numpy()
		#u = np.zeros_like(x)
		u_list.append(u)

		r = -(np.dot(x.T, x) + np.dot(u.T,u))

		x_next = A.dot(x) + u
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

	returns1 = discount_rewards(r_list, discount, center=True)
	#returns2 = discount_rewards(r2, discount, center=True)

#    r = float32(x_curr[:,0] > 0.1)
	
#    return x_list, r
	return x_curr, x_next, u_list, returns1, r_list


def add_irrelevant_features(x, x_next, extra_dim, noise_level = 0.4):

#    x_irrel= np.random.random((x.shape[0], extra_dim))
	x_irrel= noise_level*np.random.randn(x.shape[0], extra_dim)
#    x_irrel_next = x_irrel**2 + 1.0
#    x_irrel_next = x_irrel**2
#    x_irrel_next = 0.1*np.random.random((x.shape[0], extra_dim))
	x_irrel_next = noise_level*np.random.randn(x.shape[0], extra_dim)
#    x_irrel_next = x_irrel**2 + noise_level*np.random.randn(x.shape[0], extra_dim)    
#    x_irrel_next = x_irrel**2 + np.random.random((x.shape[0], extra_dim))
	
	return np.hstack([x, x_irrel]), np.hstack([x_next, x_irrel_next])


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
			return torch.cat((torch.zeros((x.shape[0], step, x.shape[2])).double(),x),dim=1)[:,:step]
		elif dir=='up':
			return torch.cat((x,torch.zeros((x.shape[0], step, x.shape[2])).double()),dim=1)[:,step:]

	elif len(x.shape) == 2: 
		if dir=='down':
			return torch.cat((torch.zeros((step, x.shape[1])).double(),x),dim=0)[:step]
		elif dir=='up':
			return torch.cat((x,torch.zeros((step, x.shape[1])).double()),dim=0)[step:]

	else:
		raise NotImplementedError('shape {shape_x} of input not corrent or implemented'.format(shape_x=x.shape))



def roll_left(x, n):  
	#return torch.cat((x[-n:], x[:-n]))
	return torch.cat((x[n:], x[:n]))



def get_selected_log_probabilities(policy_estimator, states_tensor, actions_tensor):#, batch_actions):
	action_probs = policy_estimator(states_tensor)

	if not policy_estimator.continuous:
		log_probs = torch.log(torch.clamp(action_probs[0],min=1e-5))
		if ((log_probs < -100).any()):
			pdb.set_trace()

		selected_log_probs = torch.index_select(log_probs, 1, actions_tensor)[range(len(actions_tensor)), range(len(actions_tensor))]
	else:
		n = Normal(*action_probs)
		selected_log_probs = n.log_prob(actions_tensor)
	return selected_log_probs


#################### IGNORE BELOW ##############################
# def mle_validation_loss(P_hat, policy, val_states_next_tensor, state_actions_val, n_actions, max_actions, continuous_actionspace=False, device='cpu'):

# 	squared_errors_val = torch.zeros_like(val_states_next_tensor)
# 	step_state_val = state_actions_val.to(device)

# 	with torch.no_grad():
# 		for step in range(max_actions-1):
# 			next_step_state_val = P_hat(step_state_val)
# 			squared_errors_val += shift_down((val_states_next_tensor[:,step:,:] - next_step_state_val)**2, step, max_actions)

# 			shortened_val = next_step_state_val[:,:-1,:]
# 			action_probs_val = policy(torch.DoubleTensor(shortened_val))
			
# 			if not continuous_actionspace:
# 				c_val = Categorical(action_probs_val[0])
# 				a_val = c_val.sample().type(torch.DoubleTensor).to(device)
# 				step_state_val = torch.cat((shortened_val, convert_one_hot(a_val, n_actions).unsqueeze(2)),dim=2)
# 			else:
# 				c_val = Normal(*action_probs_val)
# 				a_val = torch.clamp(c_val.rsample(), min=-2.0, max=2.0)
# 				step_state_val = torch.cat((shortened_val, a_val),dim=2)

# 	# if squared_errors_val.shape < 2:
# 	# 	squared_errors_val.unsqueeze(0)
	
# 	err_1step = torch.mean(squared_errors_val[:,1])
# 	err_5step = torch.mean(squared_errors_val[:,5])

# 	try:
# 		err_10step = torch.mean(squared_errors_val[:,10])
# 		err_50step = torch.mean(squared_errors_val[:,50])
# 		err_100step = torch.mean(squared_errors_val[:,100])
# 	except:
# 		err_10step = 0
# 		err_50step = 0
# 		err_100step = torch.mean(squared_errors_val[:,-1])

# 	print("Multistep error values:", err_1step, err_5step, err_10step, err_50step, err_100step, "\n")	

# 	return squared_errors_val



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

