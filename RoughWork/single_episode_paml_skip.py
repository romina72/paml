import numpy as np
import matplotlib.pyplot as plt
#import gym
import sys

import torch
import math
from torch import nn
from torch import optim
from torch.distributions import Categorical, Normal, MultivariateNormal
from torch.autograd import grad, gradgradcheck

import pdb
import os
from models import *
from networks import *
from utils import *
from rewardfunctions import *

# from dm_control import suite
# import gym
# import dm_control2gym

#implement saving multiple checkpoints!!!!!!

import pickle

path = '/home/romina/for_viz/'
device = 'cuda' if torch.cuda.is_available() else 'cpu'
#device = 'cpu' # .... much slower with cuda ....
loss_name = 'paml'


MAX_TORQUE = 10.
# torch.manual_seed(7)
# np.random.seed(7)

if __name__ == "__main__":
	#initialize pe 
	num_random_seeds = 1
	gen_data = False
	for rs in range(num_random_seeds):
		rs = 7
		torch.manual_seed(rs)
		np.random.seed(rs)	

		states_dim = 2
		extra_dim = 0
		salient_states_dim = states_dim - extra_dim

		actions_dim = states_dim

		A_all = {}

		A_all[10] = np.array([[0.9 , 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01],
						       [0.01, 0.2 , 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01],
						       [0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01],
						       [0.01, 0.01, 0.01, 0.6 , 0.01, 0.01, 0.01, 0.01, 0.01, 0.01],
						       [0.01, 0.01, 0.01, 0.01, 0.8 , 0.01, 0.01, 0.01, 0.01, 0.01],
						       [0.01, 0.01, 0.01, 0.01, 0.01, 0.7 , 0.01, 0.01, 0.01, 0.01],
						       [0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.1 , 0.01, 0.01, 0.01],
						       [0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.4 , 0.01, 0.01],
						       [0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.3 , 0.01],
						       [0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.5 ]])

		A_all[5] = np.array([[-0.2,  0.1,  0.1,  0.1,  0.1],
				       		[ 0.1,  0.1,  0.1,  0.1,  0.1],
				       		[ 0.1,  0.1,  0.5,  0.1,  0.1],
				       		[ 0.1,  0.1,  0.1,  0.8,  0.1],
				       		[ 0.1,  0.1,  0.1,  0.1, -0.9]])
		
		A_all[4] = np.array([[-0.2,  0.3,  0.3,  0.3],
				       		[ 0.3, -0.4,  0.3,  0.3],
				       		[ 0.3,  0.3,  0.3,  0.3],
				      		[ 0.3,  0.3,  0.3, -0.1]])
		
		A_all[3] = np.array([[-0.5, -0.5, -0.5],
       						[ 0.3, -0.2,  0.3],
       						[ 0.3,  0.3,  0.4]])

		A_all[2] = np.array([[0.9, 0.4], [-0.4, 0.9]])

		A_all[1] = np.array([0.4])


		A_numpy = A_all[salient_states_dim]
		#next, try 3000 starts, 1 ep for training, and same situation for val
		num_episodes = 1
		val_num_episodes = 100
		max_actions = 3
		num_starting_states = 500
		val_num_starting_states = 125
		num_states = max_actions + 1
		num_iters = 6000
		opt_steps = 1
		
		train = True
		use_model = True 

		discount = 0.9
		R_range = max_actions
		final_R_range = max_actions

		batch_size = num_starting_states * num_episodes
		val_batch_size = val_num_starting_states * val_num_episodes 
		# true_log_probs_grad_file = open('true_log_probs_grad.txt', 'w')
		# model_log_probs_grad_file = open('model_log_probs_grad.txt', 'w')

		#####
		true_pe_grads_file = open('true_pe_grads.txt', 'w')
		model_pe_grads_file = open('model_pe_grads.txt', 'w') 

		#true_returns_file = open('true_returns.txt', 'w')
		#model_returns_file = open('model_returns.txt', 'w') 
		######

		# dm_control2gym.create_render_mode('rs', show=False, return_pixel=True, height=240, width=320, camera_id=-1, overlays=(), depth=False, scene_option=None)

		# # env = dm_control2gym.make(domain_name="pendulum")#, task_name="balance")
		# # env.spec.id = 'dm_pendulum'
		# env = gym.make('CartPole-v0')

		# states_dim = env.observation_space.shape[0]
		# continuous_actionspace = isinstance(env.action_space, gym.spaces.box.Box)
		# if continuous_actionspace:
		# 	actions_dim = env.action_space.shape[0]
		# else:
		# 	actions_dim = env.action_space.n
		# env.seed(0)

		# errors_name = env.spec.id + '_single_episode_errors_' + loss_name + '_' + str(R_range)
		#env_name = env.spec.id

		##########for linear system setup#############
		dataset = ReplayMemory(2000000)
		validation_dataset = ReplayMemory(1000000)

		x_d = np.zeros((0,2))
		x_next_d = np.zeros((0,2))
		r_d = np.zeros((0))

		continuous_actionspace = True
		
		errors_name = 'lin_dyn_single_episode_errors_' + loss_name + '_' + str(R_range)
		env_name = 'lin_dyn'
		#########################################

		#P_hat = ACPModel(states_dim, actions_dim, clip_output=False)
		P_hat = DirectEnvModel(states_dim,actions_dim, MAX_TORQUE)
		pe = Policy(states_dim, actions_dim, continuous=continuous_actionspace, std=-2.5, max_torque=MAX_TORQUE)
		
		# P_hat.load_state_dict(torch.load('paml_trained_lin_dyn_horizon10_traj11_using1states_statesdim2_500starts_1eps.pth', map_location=device))
		#pe.load_state_dict(torch.load('policy_reinforce_cartpole.pth', map_location=device))
		#P_hat.load_state_dict(torch.load('trained_mle_300start_1eps_lin_dyn_horizon_3_traj_4_mle_trained_model.pth', map_location=device))

		# P_hat.load_state_dict(torch.load('paml_trained_lin_dyn_horizon3_traj4_using1states_500starts_1eps_10statesdim_multiplier0_1.pth', map_location=device))
		#P_hat.load_state_dict(torch.load('model_paml_checkpoint_train_True_lin_dyn_horizon3_traj4_using1states.pth', map_location=device))
		#P_hat.load_state_dict(torch.load('paml_check_point_good_1ep_300start_hor3_traj4.pth', map_location=device))
		#P_hat.load_state_dict(torch.load('model_paml_checkpoint_train_True_lin_dyn_horizon3_traj4_using1states.pth', map_location=device)) 

		P_hat.to(device).double()
		pe.to(device).double()

		for p in P_hat.parameters():
			p.requires_grad = True

		opt = optim.SGD(P_hat.parameters(), lr=1e-6, momentum=0.90, nesterov=True)
		#opt = optim.Adam(P_hat.parameters(), lr=1e-6, weight_decay=1e-8) #increase wd?
		lr_schedule = torch.optim.lr_scheduler.MultiStepLR(opt, milestones=[3000,5000,6000], gamma=0.1)
		#1. Gather data, 2. train model with mle 3. reinforce 4. run policy, add new data to data

		#1. Gather data
		losses = []
		val_losses = []
		grads = []
		pe_params = []
		r_norms = []
		best_loss = 20

		#unroll_num = num_states - R_range # T_i - j

		# list_log_sigmas = [-8.0, -6.0, -4.0, -2.0, 0.0, 2.0, 4.0, 6.0, 8.0]
		# list_starting_states = []
		# for ststate in range(num_starting_states):
		# 	x_0 = 2*np.random.random(size=(2,)) - 0.5
		# 	list_starting_states.append(x_0)

		# sigma_returns_dict = {}

		# for log_sigma in list_log_sigmas:
		# 	print(log_sigma)
		# 	pe = Policy(states_dim, actions_dim, continuous=continuous_actionspace, std=log_sigma)
		# 	pe.to(device).double()
		# 	sigma_returns_dict[log_sigma] = []

		# 	for x_0 in list_starting_states:
		# 		print(x_0)
		# 		dataset = ReplayMemory(10000)
		# 		for ep in range(num_episodes):
		# 			x_tmp, x_next_tmp, u_list, _, r_list = lin_dyn(max_actions, pe, [], x=x_0, discount=0.0)
		# 			for x, x_next, u, r in zip(x_tmp, x_next_tmp, u_list, r_list):
		# 				dataset.push(x, x_next, u, r)

		# 		#assuming samples are disjoint
		# 		batch = dataset.sample(batch_size, structured=True, max_actions=max_actions, num_episodes=num_episodes, num_starting_states=1)

		# 		states_prev = torch.zeros((batch_size, max_actions, states_dim)).double().to(device)
		# 		states_next = torch.zeros((batch_size, max_actions, states_dim)).double().to(device)
		# 		rewards = torch.zeros((batch_size, max_actions)).double().to(device)
		# 		actions_tensor = torch.zeros((batch_size, max_actions, actions_dim)).double().to(device)
		# 		discounted_rewards_tensor = torch.zeros((batch_size, max_actions, 1)).double().to(device)

		# 		for b in range(batch_size):
		# 			states_prev[b] = torch.tensor([samp.state for samp in batch[b]]).double().to(device)
		# 			states_next[b] = torch.tensor([samp.next_state for samp in batch[b]]).double().to(device)
		# 			rewards[b] = torch.tensor([samp.reward for samp in batch[b]]).double().to(device)
		# 			actions_tensor[b] = torch.tensor([samp.action for samp in batch[b]]).double().to(device)
		# 			discounted_rewards_tensor[b] = discount_rewards(rewards[b].unsqueeze(1), discount, center=False).to(device)
		# 		state_actions = torch.cat((states_prev,actions_tensor), dim=2)

		# 		true_log_probs_t = get_selected_log_probabilities(pe, states_prev.view(-1,states_dim), actions_tensor.view(-1,actions_dim)).view(batch_size,max_actions,actions_dim)

		# 		sigma_returns_dict[log_sigma].append(true_log_probs_t.mean(dim=0)[1].detach().numpy())

		# np.save(os.path.join(path,'log_probs_log_sigma_same_starts_comparison.npy'), sigma_returns_dict)

		fname_training = 'training_{}_statesdim_{}_traj_{}.pickle'.format(rs, states_dim, max_actions+1)
		fname_val = 'val_{}_statesdim_{}_traj_{}.pickle'.format(rs, states_dim, max_actions+1)
		# with open(fname_training, 'rb') as data:
		# 	pdb.set_trace()
		# 	dataset = pickle.load(data)

		# fname_val = 'validation_' + str(rs) + '.pickle'
		# with open(fname_val, 'rb') as data:
		# 	validation_dataset = pickle.load(data)
		if gen_data:
		#if True:
			for ststate in range(num_starting_states):
				x_0 = 2*np.random.random(size=(salient_states_dim,)) - 0.5
				for ep in range(num_episodes):
					x_tmp, x_next_tmp, u_list, _, r_list = lin_dyn(A_numpy, max_actions, pe, [], x=x_0, extra_dim=extra_dim, discount=0.0)
					# x_tmp = add_irrelevant_features(x_tmp, extra_dim)
					# x_next_tmp = add_irrelevant_features(x_next_tmp, extra_dim)

					for x, x_next, u, r in zip(x_tmp, x_next_tmp, u_list, r_list):
						dataset.push(x, x_next, u, r)

			with open(fname_training, 'wb') as output:
				pickle.dump(dataset, output)


			#get validation data
			for ststate in range(val_num_starting_states):
				x_0 = 2*np.random.random(size = (salient_states_dim,)) - 0.5
				for ep in range(val_num_episodes):
					x_tmp, x_next_tmp, u_list, _, r_list= lin_dyn(A_numpy, max_actions, pe, [], x=x_0, extra_dim=extra_dim,discount=0.0)

					# x_tmp = add_irrelevant_features(x_tmp, extra_dim)
					# x_next_tmp = add_irrelevant_features(x_next_tmp, extra_dim)

					for x, x_next, u, r in zip(x_tmp, x_next_tmp, u_list, r_list):
						validation_dataset.push(x, x_next, u, r)

			with open(fname_val, 'wb') as output:
				pickle.dump(validation_dataset, output)

		else:
			# for ststate in range(num_starting_states):
			# 	x_0 = 2*np.random.random(size=(2,)) - 0.5
			# 	for ep in range(num_episodes):
			# 		x_tmp, x_next_tmp, u_list, _, r_list = lin_dyn(max_actions, pe, [], x=x_0, discount=0.0)
			# 		for x, x_next, u, r in zip(x_tmp, x_next_tmp, u_list, r_list):
			# 			dataset.push(x, x_next, u, r)


			with open(fname_training, 'rb') as data:
				dataset = pickle.load(data)

			#get validation data
			# for ststate in range(val_num_starting_states):
			# 	x_0 = 2*np.random.random(size = (2,)) - 0.5
			# 	for ep in range(num_episodes):
			# 		x_tmp, x_next_tmp, u_list, r_tmp, _ = lin_dyn(max_actions, pe, [], x=x_0)
			# 		for x, x_next, u, r in zip(x_tmp, x_next_tmp, u_list, r_tmp):
			# 			validation_dataset.push(x, x_next, u, r)

			with open(fname_val, 'rb') as data:
				validation_dataset = pickle.load(data)

			testing_order = []
			kwargs = {
					'dataset'    : dataset,
					'train'		 : train,
					'env_name'	 : env_name,
					'device'	 : device,
					'num_starting_states' : num_starting_states,
					'num_episodes': num_episodes,
					'batch_size' : batch_size, 
					'max_actions': max_actions, 
					'states_dim' : states_dim, 
					'actions_dim': actions_dim,
					'num_states' : num_states,
					'R_range'    : R_range,#range(max_action), #add in function to check if list or single number, if list, increase R_range when the loss goes below a threshold ... around 1000 episodes 
					'discount'   : discount,
					'true_pe_grads_file': true_pe_grads_file, 
					'model_pe_grads_file': model_pe_grads_file,
					'losses'     : losses,
					'opt'        : opt,
					'opt_steps'  : opt_steps,
					'num_iters'  : int(num_iters/60),
					'lr_schedule': lr_schedule,
					'use_model' : use_model,
					'testing_order': testing_order,
					'policy_states_dim' : salient_states_dim,
					'end_of_trajectory' : 1,
					'A_numpy' : A_numpy
					}

			reached_R_range = R_range

			true_losses = []
			for t in range(1):
				kwargs['train'] = False
				kwargs['dataset'] = validation_dataset
				kwargs['num_starting_states'] = val_num_starting_states
				kwargs['losses'] = true_losses
				kwargs['batch_size'] = val_batch_size
				kwargs['num_episodes'] = val_num_episodes
				kwargs['R_range'] = final_R_range

				kwargs['use_model'] = False

				# print('validation loss')
				P_hat.paml(pe, **kwargs)

			print(sum(true_losses)/len(true_losses))


			# true_losses = []
			# for t in range(10):
			# 	kwargs['train'] = False
			# 	kwargs['dataset'] = dataset
			# 	kwargs['num_starting_states'] = num_starting_states
			# 	kwargs['losses'] = true_losses
			# 	kwargs['batch_size'] = batch_size
			# 	kwargs['num_episodes'] = num_episodes
			# 	kwargs['R_range'] = final_R_range

			# 	kwargs['use_model'] = False

			# 	# print('validation loss')
			# 	P_hat.paml(pe, **kwargs)

			# print(sum(true_losses)/len(true_losses))
			#pdb.set_trace()

			kwargs['use_model'] = use_model	
			iters = 60 if train else 3
			for i in range(iters):
				kwargs['train'] = False
				kwargs['dataset'] = validation_dataset
				kwargs['num_starting_states'] = val_num_starting_states
				kwargs['losses'] = val_losses
				kwargs['batch_size'] = val_batch_size
				kwargs['num_episodes'] = val_num_episodes
				kwargs['R_range'] = final_R_range


				# print('validation loss')
				P_hat.paml(pe, **kwargs)
				#print(val_losses)

				#pdb.set_trace()

				#Train
				kwargs['train'] = train
				kwargs['dataset'] = dataset
				kwargs['num_starting_states'] = num_starting_states
				kwargs['losses'] = losses
				kwargs['batch_size'] = batch_size
				kwargs['num_episodes'] = num_episodes
				kwargs['R_range'] = reached_R_range
				#kwargs['opt_steps'] = opt_steps if i ==0 else 1
				reached_R_range = P_hat.paml(pe, **kwargs)
				#print(losses)
				#pdb.set_trace()

			#np.save(os.path.join(path,loss_name+'testing_order'),np.asarray(testing_order))

			#print(sum(losses) / float(len(losses)))
			#print(sum(val_losses) / float(len(val_losses)))

			# np.save(os.path.join(path,'validation_' + loss_name+'_rs'+str(rs)+'_finalhorizon_'+str(reached_R_range)),np.asarray(val_losses))
			# np.save(os.path.join(path,loss_name+'_rs'+str(rs)+'_finalhorizon_'+str(reached_R_range)),np.asarray(losses))



			####################. for log_sigma comparisons ################################
			# x_0 = 2*np.random.random(size=(2,)) - 0.5

			# for ls in range(-2,-9,-1):
			# 	losses = []
			# 	log_sigma = ls*0.5
			# 	dataset = ReplayMemory(500000)
			# 	print(log_sigma)
			# 	pe = Policy(states_dim, actions_dim, continuous=continuous_actionspace, std=log_sigma)
			# 	P_hat = DirectEnvModel(states_dim,actions_dim, MAX_TORQUE)
			# 	P_hat.to(device).double()
			# 	pe.to(device).double()

			# 	for p in P_hat.parameters():
			# 		p.requires_grad = True

			# 	opt = optim.SGD(P_hat.parameters(), lr=1e-6, momentum=0.90, nesterov=True)
			# 	lr_schedule = torch.optim.lr_scheduler.MultiStepLR(opt, milestones=[1000,1200,2000], gamma=0.1)
			# 	for ep in range(num_episodes):
			# 		x_tmp, x_next_tmp, u_list, _, r_list = lin_dyn(max_actions, pe, [], x=x_0, discount=0.0)
			# 		for x, x_next, u, r in zip(x_tmp, x_next_tmp, u_list, r_list):
			# 			dataset.push(x, x_next, u, r)


			# 	kwargs = {
			# 		'dataset'    : dataset,
			# 		'train'		 : train,
			# 		'env_name'	 : env_name,
			# 		'device'	 : device,
			# 		'num_starting_states' : num_starting_states,
			# 		'num_episodes': num_episodes,
			# 		'batch_size' : batch_size, 
			# 		'max_actions': max_actions, 
			# 		'states_dim' : states_dim, 
			# 		'actions_dim': actions_dim,
			# 		'num_states' : num_states,
			# 		'R_range'    : R_range,#range(max_action), #add in function to check if list or single number, if list, increase R_range when the loss goes below a threshold ... around 1000 episodes 
			# 		'discount'   : discount,
			# 		'true_pe_grads_file': true_pe_grads_file, 
			# 		'model_pe_grads_file': model_pe_grads_file,
			# 		'losses'     : losses,
			# 		'opt'        : opt,
			# 		'opt_steps'  : opt_steps,
			# 		'num_iters'  : num_iters,
			# 		'lr_schedule': lr_schedule
			# 		}
			# 	#Train
			# 	kwargs['train'] = True
			# 	kwargs['dataset'] = dataset
			# 	kwargs['num_starting_states'] = num_starting_states
			# 	kwargs['losses'] = losses
			# 	kwargs['R_range'] = R_range
			# 	best_loss = P_hat.paml(pe, **kwargs)

				# print(os.path.join(path,loss_name + '_' + str(log_sigma)))
				# np.save(os.path.join(path,loss_name + '_' + str(log_sigma)),np.asarray(losses))
			########################################################################################

			#### end of training, check on validation data
			# kwargs['train'] = False
			# kwargs['dataset'] = validation_dataset
			# kwargs['num_starting_states'] = val_num_starting_states
			# kwargs['losses'] = []
			# kwargs['batch_size'] = val_batch_size
			# kwargs['R_range'] = final_R_range

			# print('Trained paml loss on validation set')
			#P_hat.paml(pe, **kwargs)

			print('---------------------------------------------------------------------')
			#P_hat.load_state_dict(torch.load('lin_dyn_paml_trained_model.pth', map_location=device))
			#P_hat.load_state_dict(torch.load('lin_dyn_mle_hor_2_traj_20_batch_1000_sameStartState.pth', map_location=device))

			##########################
			val_loss = 0
			for i in range(val_num_starting_states):
				val_data = validation_dataset.sample(val_batch_size, structured=True, max_actions=max_actions, num_episodes_per_start=val_num_episodes, num_starting_states=val_num_starting_states, start_at=None)

				val_states_prev = torch.zeros((val_batch_size, max_actions, states_dim)).double()
				val_states_next = torch.zeros((val_batch_size, max_actions, states_dim)).double()
				val_rewards = torch.zeros((val_batch_size, max_actions)).double()
				val_actions_tensor = torch.zeros((val_batch_size, max_actions, actions_dim)).double()

				for v in range(val_batch_size):
					val_states_prev[v] = torch.tensor([samp.state for samp in val_data[v]]).double()
					val_states_next[v] = torch.tensor([samp.next_state for samp in val_data[v]]).double()
					val_rewards[v] = torch.tensor([samp.reward for samp in val_data[v]]).double()
					val_actions_tensor[v] = torch.tensor([samp.action for samp in val_data[v]]).double()

				val_state_actions = torch.cat((val_states_prev,val_actions_tensor), dim=2)
				val_loss += P_hat.mle_validation_loss(A_numpy, val_states_next, val_state_actions, pe, final_R_range, use_model=use_model, salient_dims=salient_states_dim)

			val_loss = val_loss / val_num_starting_states
			print('MLE loss on mleorpaml-trained model average over validation data: ', val_loss.detach())


			# print('---------------------------------------------------------------------')
			# kwargs['train'] = False
			# kwargs['dataset'] = validation_dataset
			# kwargs['num_starting_states'] = val_num_starting_states
			# kwargs['losses'] = []
			# kwargs['batch_size'] = val_batch_size
			# kwargs['R_range'] = final_R_range


			# P_hat.load_state_dict(torch.load('lin_dyn_horizon_10_traj_12_mle_trained_model.pth', map_location=device))

			# print('Calculating PAML loss on MLE_trained model .... ')
			# P_hat.paml(pe, **kwargs)

			print('---------------------------------------------------------------------')
			#Put below in function
			val_loss = 0
			for i in range(val_num_starting_states):
				val_data = validation_dataset.sample(val_batch_size, structured=True, max_actions=max_actions, num_episodes_per_start=val_num_episodes, num_starting_states=val_num_starting_states, start_at=None)

				val_states_prev = torch.zeros((val_batch_size, max_actions, states_dim)).double()
				val_states_next = torch.zeros((val_batch_size, max_actions, states_dim)).double()
				val_rewards = torch.zeros((val_batch_size, max_actions)).double()
				val_actions_tensor = torch.zeros((val_batch_size, max_actions, actions_dim)).double()

				for v in range(val_batch_size):
					val_states_prev[v] = torch.tensor([samp.state for samp in val_data[v]]).double()
					val_states_next[v] = torch.tensor([samp.next_state for samp in val_data[v]]).double()
					val_rewards[v] = torch.tensor([samp.reward for samp in val_data[v]]).double()
					val_actions_tensor[v] = torch.tensor([samp.action for samp in val_data[v]]).double()

				val_state_actions = torch.cat((val_states_prev,val_actions_tensor), dim=2)
				val_loss += P_hat.mle_validation_loss(A_numpy, val_states_next, val_state_actions, pe, final_R_range, use_model=False, salient_dims=salient_states_dim)

			val_loss = val_loss / val_num_starting_states
			print('MLE loss on true dynamics average over validation data: ', val_loss.detach())
			########################


			#### do MLE loss on paml-trained model and mle-trained model
			#####################

			# elif i == num_iters-2:
			# 	model_loss = P_hat.mle_validation_loss(states_next, state_actions.to(device), pe, R_range)
			# 	print("ep: {}, mle_loss on PAML_trained = {:.7f}".format(i, model_loss.data.cpu()))

			# 	model_loss = P_hat.mle_validation_loss(states_next, state_actions.to(device), pe, R_range)
			# 	print("ep: {}, mle_loss on MLE_trained = {:.7f}".format(i, model_loss.data.cpu()))


		# print('saving multi-step errors ...')

		# print(best_loss)
		#print(os.path.join(path,loss_name))
		# np.save(os.path.join(path,'grads'),np.asarray(grads))
		#np.save(os.path.join(path,'paml_rewards_norm_rs'+str(rs)),np.asarray(r_norms))

	# np.save(os.path.join(path,loss_name +'_pe_params'),np.asarray(pe_params))