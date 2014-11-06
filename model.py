import theano
import theano.tensor as T
import numpy         as np
from theano.printing import Print
from theano_toolkit import utils as U
from theano_toolkit.parameters import Parameters
import controller
import head
import scipy

def cosine_sim(k,M):
	k_unit = k / T.sqrt(T.sum(k**2))
	k_unit = T.patternbroadcast(k_unit.reshape((1,k_unit.shape[0])),(True,False))
	k_unit.name = "k_unit"
	M_lengths = T.patternbroadcast(T.sqrt(T.sum(M**2,axis=1)).reshape((M.shape[0],1)),(False,True))
	M_unit = M / M_lengths
	M_unit.name = "M_unit"
#	M_unit = Print("M_unit")(M_unit)
	return T.sum(k_unit * M_unit,axis=1)

def build_step(P,controller,controller_size,mem_size,mem_width,similarity=cosine_sim,shift_width=3):
	
	shift_conv = scipy.linalg.circulant(np.arange(mem_size)).T[np.arange(-(shift_width//2),(shift_width//2)+1)][::-1]
	print shift_conv

	P.memory_init = 0.1 * np.random.randn(mem_size,mem_width)
	P.weight_init  = 0.1 * np.random.randn(mem_size)

	memory_init = P.memory_init
	weight_init = U.vector_softmax(P.weight_init)

	heads = [head.build(P,0,controller_size,mem_width,mem_size,shift_width)]
	
	def build_memory_curr(M_prev,erase_head,add_head,weight):
		weight = weight.dimshuffle((0,'x'))

		erase_head = erase_head.dimshuffle(('x',0))
		add_head   = add_head.dimshuffle(('x',0))

		M_erased = M_prev   * (1 - (weight * erase_head))
		M_curr   = M_erased +      (weight * add_head)
		return M_curr
	
	def build_read(M_curr,weight_curr):
		return T.dot(weight_curr, M_curr)

	def shift_convolve(weight,shift):
		shift = shift.dimshuffle((0,'x'))
		return T.sum(shift * weight[shift_conv],axis=0)


	def build_head_curr(weight_prev,M_curr,head,input_curr):
		"""
		This function is best described by Figure 2 in the paper.
		"""
		key,beta,g,shift,gamma,erase,add = head(input_curr)

		# 3.3.1 Focusing b Content
		weight_c = U.vector_softmax(beta * similarity(key,M_curr))

		# 3.3.2 Focusing by Location
		weight_g       = g * weight_c + (1 - g) * weight_prev

		weight_shifted = shift_convolve(weight_g,shift)

		weight_sharp   = weight_shifted ** gamma
		weight_curr    = weight_sharp / T.sum(weight_sharp)

		return weight_curr,erase,add
	
	def step(input_curr,M_prev,weight_prev):
		#print read_prev.type
		
		read_prev = build_read(M_prev,weight_prev)
		output,controller_hidden = controller(input_curr,read_prev)

		weight_curr,erase,add = build_head_curr(weight_prev,M_prev,heads[0],controller_hidden)

		M_curr = build_memory_curr(M_prev,erase,add,weight_curr)
		
		#print [i.type for i in [erase_curr,add_curr,key_curr,shift_curr,beta_curr,gamma_curr,g_curr,output]]
		#print weight_curr.type
		return M_curr,weight_curr,output
	return step,[memory_init,weight_init,None]

def build(P,mem_size,mem_width,controller_size,ctrl):
	step,outputs_info = build_step(P,ctrl,controller_size,mem_size,mem_width)
	def predict(input_sequence):
		outputs,_ = theano.scan(
				step,
				sequences    = [input_sequence],
				outputs_info = outputs_info
			)
		return outputs
	return predict


