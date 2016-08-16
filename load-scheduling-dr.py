import random as r
import simpy
import pprint as pp
import datetime
import numpy as np
from matplotlib import pyplot as plt
import time

# holding seed constant will cause random numbers to have the 
# same values across trials, vary seed to batch experiments 
r.seed(12345)

WASHER = {'name':'Washer','power':1000, 'DR':1, 'lowbound':0, 'highbound':10, 'noevents':1, 'duration':1}
DRYER = {'name':'Dryer','power':500, 'DR':1, 'lowbound':6, 'highbound':17, 'noevents':2, 'duration':2}
HEATER = {'name':'Heater','power':100, 'DR':1, 'lowbound':0, 'highbound':24, 'noevents':10, 'duration':2}
SPEAKERS = {'name':'Speakers','power':500, 'DR':1, 'lowbound':18, 'highbound':24, 'noevents':3, 'duration':1}
APPLIANCES = {'Washer':WASHER, 'Dryer':DRYER, 'Heater':HEATER}

# cost of energy over the course of a day, 24 hours
TOU = [15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 15, 22, 22, 34, 34, 34, 34, 34, 34, 22, 22, 15, 15, 15] 


class HomeEnergyAutomationDevice:

	'''
		holds all appliances
		starts demand_response process
	'''

	DR_window = (16,19)

	def __init__(self, APPLIANCES, env, store):

		self.env = env
		self.app_array = APPLIANCES
		self.appliances = []

		for i in self.app_array:
			# create instance of Appliance and append to array
			self.appliances.append(Appliance(self.app_array[i], env, store))

			# add string of appliance name to filterstore
			store.put(self.app_array[i]['name'])

		self.DR = env.process(self.demand_response(APPLIANCES, store, env))


	def demand_response(self, APPLIANCES, store, env):
		# creates a DR process during the DR window
		yield env.timeout(self.DR_window[0])
		# check each appliance instance
		for i in self.appliances:
			# check each start time in array
			for j in i.start_times:
				# is start time scheduled in DR window?
				if ((j+i.duration) >= self.DR_window[0]) and ((j+i.duration) <= self.DR_window[1]):
					# is load DR-able
					if i.DR == 1:
						i.is_operating.interrupt()


class Appliance:

	kWh_per_hour = [0] * 24
	curtailed = [0] * 24
	shifted = [0] * 24

	def __init__(self, appliance_info, env, store):

		# takes input of appliance info dictionary, allocates parameters appropriately
		self.env = env
		self.power = appliance_info['power']
		self.name = appliance_info['name']
		self.DR = appliance_info['DR']
		self.noevents = appliance_info['noevents']
		self.duration = appliance_info['duration']
		self.lowbound = appliance_info['lowbound']
		self.highbound = appliance_info['highbound']

		# return noevents number of events between lowbound and highbound
		inter = np.linspace(self.lowbound, self.highbound, self.noevents+1)
		intervals = []
		# round off inter
		for i in inter:
			intervals.append(int(i))

		self.start_times = []

		for first, second in zip(intervals, intervals[1:]):
			self.start_times.append(r.randint(first,second))

		self.is_operating = env.process(self.operation(env, store))
		print "%s %s Event(s)" % (len(self.start_times), self.name)
		prev = 0
		for i in self.start_times:
			if i-prev < self.duration:
				i = prev + self.duration
			print ("AT: %s" % (i))
			prev = i
		print ""


	def operation(self, env, store):

		'''
			self is an appliance
			can interact with Appliance class poperties 
			lives in an environment env
			interacts with a store
		'''

		end_time = 0
		# loops over number of times appliance is supposed to start
		for i in self.start_times:
			# checks if start time is before end time, AKA appliance is still in use
			gap = i - end_time
			try:
				# if gap is < 1, proceed without waiting
				if gap <= 0:
					yield env.timeout(0)
				# if not, wait an appropriate amount of time
				else:
					yield env.timeout(gap)

				# pull appliance from store, start using power
				yield store.get(lambda x: x == self.name)
				duration = self.duration
				print('%10s %7s %5s %i' % ("STARTED:",self.name,"AT: ", env.now))

				# the appliance is on, use power and decrement duration
				while duration > 0:
					Appliance.kWh_per_hour[env.now] += self.power
					yield env.timeout(1)
					duration -= 1

				# appliance is done, put back in the store
				yield store.put(self.name)
				print "%10s %7s %5s %i" % ("FINISHED:",self.name, "AT: ", env.now)

				end_time = env.now

			# if appliance gets DRed then curtail load
			except simpy.Interrupt as i:
				Appliance.curtailed[env.now] += self.power
				store.put(self.name)
				print "%10s %7s %5s %i" % ("DRed:",self.name, "AT: ", env.now)
				Appliance.shifted[HomeEnergyAutomationDevice.DR_window[1]] += self.power
				# TODO reschedule DRed event
	

def simulate_day(num, Appliance):

	'''
	this is a generator that "holds" num number of trials of a single day of simulation

	inputs:
		num - count of simulations to do
		Appliance - class Appliance, acts as storage for cumulative values for each day/simulation
	
	outputs:
		Appliance.kWh_per_hour - 24 slot list holding power usage per hour
		Appliance.curtailed - 24 slot list holding curtailed usage per hour
	'''

	i = 0

	while i < num:

		# header for looks
		now = datetime.datetime.now()
		print ""
		print "~~~~~~~~~~~~~~~~~~~~~~~~~~~"
		print "DR SIM #%s START AT %s:%02d:%02d" % (i+1, now.hour, now.minute, now.second)
		print "~~~~~~~~~~~~~~~~~~~~~~~~~~~"
		print ""
		print "Daily Schedule"
		print "--------------"
		print ""

		# initialize simpy environment
		env = simpy.Environment()
		# store will hold names of unused appliances
		apps = simpy.FilterStore(env)
		# creates HEAD device, which creates all of the appliances
		HEAD = HomeEnergyAutomationDevice(APPLIANCES, env, apps)
		# run simulation for 1 day
		env.run(until=24)

		# returns scheduled demand and curtailed demand
		yield Appliance.kWh_per_hour, Appliance.curtailed, Appliance.shifted

		# reset for next simulation
		Appliance.kWh_per_hour = [0] * 24
		Appliance.curtailed = [0] * 24
		Appliance.shifted = [0] * 24

		i += 1

def main(num_sims, inter_frame_delay):

	# make index
	x = range(num_sims)
	# TODO make timesteps finer
	# TODO add more appliances -- get a sexy load curve
	# TODO separate energy from power

	# make plots non-blocking
	plt.ion()
	fig = plt.figure(figsize = (10,10))

	# dynamic title TODO make dynamic
	plt.title("Appliance Usage")

	# initialize series with all zeros
	cum_energy_series = [0] * num_sims
	DR_series = [0] * num_sims

	ax1 = fig.add_subplot(3, 1, 1)

	# visualize DR range
	plt.plot((16, 16), (0, 1500), 'r--')
	plt.plot((19, 19), (0, 1500), 'r--')

	ax2 = fig.add_subplot(3, 1, 2)
	ax3 = fig.add_subplot(3, 1, 3)

	ax1.set_ylabel("Watts")
	ax2.set_ylabel("Electricity Cost")
	ax3.set_ylabel("DR Savings")

	ax1.set_xlabel("Hour")
	ax2.set_xlabel("Sim Number")
	ax3.set_xlabel("Sim Number")

	cum_energy_trace, = ax2.plot(range(num_sims),cum_energy_series)
	DR_trace, = ax3.plot(range(num_sims), DR_series)

	energy_spend_tot = 0
	DR_money_tot = 0

	time.sleep(.2)
	plt.show()

	trial = 0
	cumulative_watt_schedule = [0] * 24
	cumulative_DR_schedule = [0] * 24
	cumulative_shift_schedule = [0] * 24

	# ask for some number of trials, plot each one
	for watt_schedule, DR_schedule, shift_schedule in simulate_day(num_sims, Appliance):

		# generate three sets of bars, one for demand, one for curtailed demand, and another for rescheduled demand
		power_schedule_bars = ax1.bar(range(24), watt_schedule, 1)
		curtailed_schedule_bars = ax1.bar(range(24), DR_schedule, 1)
		shifted_schedule_bars = ax1.bar(range(24), shift_schedule, 1)


		# cycle through each timestep
		for i in range(24):

			cumulative_watt_schedule[i] += watt_schedule[i]
			cumulative_DR_schedule[i] += DR_schedule[i]
			cumulative_shift_schedule[i] += shift_schedule[i]

			power_schedule_bars[i].set_height(cumulative_watt_schedule[i])
			curtailed_schedule_bars[i].set_height(cumulative_DR_schedule[i])
			shifted_schedule_bars[i].set_height(cumulative_shift_schedule[i])

			ax1.set_ylim([0,max(max(cumulative_watt_schedule, max(cumulative_DR_schedule)))])
			# power gets plotted in blue, DR gets plotted in red
			if watt_schedule[i] != 0:
				power_schedule_bars[i].set_color('b')
			elif DR_schedule[i] != 0:
				curtailed_schedule_bars[i].set_color('r')
			elif shifted_schedule_bars[i] != 0:
				shifted_schedule_bars[i].set_color('g')
			else:
				pass		


		daily_energy_spend = 0
		for hourly, price in zip(watt_schedule, TOU):
			# .001 is kwh per watt hour
			daily_energy_spend += hourly * (.001) * price

		energy_spend_tot += daily_energy_spend/100
		cum_energy_series[trial] = energy_spend_tot

		cum_energy_trace.set_xdata(x[:num_sims])
		cum_energy_trace.set_ydata(cum_energy_series)
		ax2.set_ylim([0,max(cum_energy_series)])


		daily_dr_save = 0
		for curtail, price in zip(DR_schedule, TOU):
			daily_dr_save += curtail * price * .001

		DR_money_tot += daily_dr_save/100
		DR_series[trial] = DR_money_tot

		DR_trace.set_xdata(x[:num_sims])
		DR_trace.set_ydata(DR_series)
		ax3.set_ylim([0,DR_money_tot])

		trial += 1

		# re-draw figure
		time.sleep(inter_frame_delay)
		fig.canvas.draw()

		# TODO fix axes

		# reset bar charts for next run
		for i in range(24):
			power_schedule_bars[i].set_height(0)
			curtailed_schedule_bars[i].set_height(0)	


	time.sleep(3)

if __name__ == '__main__':
	main(30, .05)

	plt.close()

