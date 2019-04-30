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
import pdb

from utils import *
from collections import namedtuple
import random


device='cpu'

def init_weights(m):
	if isinstance(m, nn.Linear):
		nn.init.normal_(m.weight, mean=0., std=0.1)
		nn.init.constant_(m.bias, 0.1)
		

Transition = namedtuple('Transition',('state', 'next_state', 'action', 'reward'))

# Using PyTorch's Tutorial
class ReplayMemory(object):

	def __init__(self, size):
		self.size = size
		self.memory = []
		self.position = 0

	def push(self, *args):
		"""Saves a transition."""
		
		if len(self.memory) < self.size:
			self.memory.append(None)

		self.memory[self.position] = Transition(*args)
		self.position = (self.position + 1) % self.size

	def clear(self):
		self.memory = []
		self.position = 0

	def sample(self, batch_size, structured=False, max_actions=10, num_episodes_per_start=10, num_starting_states=5, start_at=None):
		if structured:
			#fix this : batch_size and num_episodes_per_start should be evenly divisible .. enforce it 
			#batch_size = number of episodes to return
			#max_actions = constant that is the length of the episode
			batch = np.empty(batch_size, object)
			num_starts_per_batch = int(batch_size/num_episodes_per_start)

			if start_at:
				starting_state = np.linspace(start_at, start_at + num_starts_per_batch, num=num_starts_per_batch)
			else:
				#this is the problem, as long as order is fixed, the loss is smooth, when order changes, everything gets messed up
				#starting_state = np.random.choice(range(num_starting_states), num_starts_per_batch, replace=False)
				# print(starting_state)
				starting_state = range(num_starting_states)
				#starting_state = np.array([8, 5, 0, 2, 1, 9, 7, 3, 6, 4])
				#starting_state = np.array([6, 7, 8, 9, 0, 1, 2, 3, 4, 5])
			#starting_state is a list now
			
			ep = np.zeros((num_starts_per_batch, num_episodes_per_start))
			start_id = np.zeros((num_starts_per_batch, num_episodes_per_start))

			for start in range(num_starts_per_batch):
				#pdb.set_trace()
				#ep[start] = np.random.choice(range(num_episodes_per_start), num_episodes_per_start, replace=False)
				ep[start] = range(num_episodes_per_start)
				start_id[start] = ep[start] * max_actions + starting_state[start]*num_episodes_per_start * max_actions

			start_id = start_id.reshape(batch_size).astype(int)
			for b in range(batch_size):
				batch[b] = self.memory[start_id[b]:start_id[b]+max_actions]
				if batch[b] == []:
					print('empty batch')
					pdb.set_trace()

			return batch

		else:
			return random.sample(self.memory, batch_size)

	def __len__(self):
		return len(self.memory)



class Policy(nn.Module):
	def __init__(self, in_dim, out_dim, continuous=False, std=-0.8, max_torque=1., action_multiplier=0.1):#-0.8 GOOD
		super(Policy, self).__init__()
		self.n_actions = out_dim
		self.continuous = continuous
		self.max_torque = max_torque
		self.action_multiplier = action_multiplier
		self.lin1 = nn.Linear(in_dim, 8)
		self.relu = nn.ReLU()
		#self.lin2 = nn.Linear(32, 16)
		#self.theta = nn.Linear(4, out_dim)
		self.theta = nn.Linear(8, out_dim)

		#self.value_head = nn.Linear(4, 1)

		torch.nn.init.xavier_uniform_(self.lin1.weight)
		torch.nn.init.xavier_uniform_(self.theta.weight)

		if continuous:
			#self.log_std = nn.Linear(16, out_dim)
			self.log_std = nn.Parameter(torch.ones(out_dim) * std, requires_grad=True)
			#self.log_std = (torch.ones(out_dim) * std).type(torch.DoubleTensor)

	def forward(self, x):
		#phi = self.relu(self.lin1(x))
		if not self.continuous:
			y = self.theta(phi)
			out = nn.Softmax(dim=-1)(y)
			out = torch.clamp(out, min=-1e-4, max=100)
			return out, 0

		else:
			x = self.theta(self.relu(self.lin1(x)))
			mu = nn.Tanh()(x)
			#sigma = torch.exp(self.log_std(phi))
			sigma = self.log_std.exp().expand_as(mu)

			#values = self.value_head(x)
			return mu, sigma


	def sample_action(self, x):
		action_probs = self.forward(x)

		if not self.continuous:
			c = Categorical(action_probs[0])
			a = c.sample() 
			a = convert_one_hot(a.double(), n_actions).unsqueeze(2)
			pdb.set_trace()
			#the dim of this could be wrong due to change to batch_size. NOT TESTED
		else:
			c = Normal(*action_probs)
			#a = 0.1*torch.clamp(c.rsample(), min=-self.max_torque, max=self.max_torque)
			a = self.action_multiplier * c.rsample()

		return a#, values

class Value(nn.Module):
	def __init__(self, states_dim, actions_dim):
		super(Value, self).__init__()
		self.lin1 = nn.Linear(states_dim+actions_dim, 8)
		self.relu = nn.ReLU()
		self.theta = nn.Linear(8, 1)

		torch.nn.init.xavier_uniform_(self.lin1.weight)
		torch.nn.init.xavier_uniform_(self.theta.weight)

	def forward(self, x):
		x = self.relu(self.lin1(x))
		values = self.theta(x)
		return values