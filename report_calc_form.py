#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys, json
import inspect
import operator
import math

# From http://code.activestate.com/recipes/66062-determining-current-function-name/
self_dir = os.path.dirname(sys._getframe().f_code.co_filename)
sys.path.append(self_dir)
import report_calc
from rc_functions.rc_functions import RCClassFnExtension
from rc_functions.rc_functions import RCStaticFnExtension

DEBUG = 0

with open( self_dir + '/log.txt', 'w') as log_handle:
	log_handle.write( "Starting ...\n")
		
rulesets = None
rc_functions = None

def log(message):
	if DEBUG== 1:
		with open( self_dir + '/log.txt', 'a') as log_handle:
			log_handle.write(message)

def loglines(lines):
	if DEBUG== 1:
		with open( self_dir + '/log.txt', 'a') as log_handle:
			log_handle.writelines(lines)
						
# Populate list of rules. (rules_file is a HistoryDatasetAssociation)
def get_rule_section(rules_file):

	global rulesets
	log( "\nget_rule_section() ")
	log(rules_file.file_name)
			
	items = []
	
	if rules_file:

		log( "\ngetRulesets()  ")

		try:
			with open(rules_file.file_name, 'r') as rules_handle:
				rulefileobj =  json.load(rules_handle)
				log("Rule file json parsed")
				rulesets = rulefileobj['rulesets']
				log("\nRule sets loaded")
				#loglines(rulesets)
				
		except Exception,e: 
			log(str(e))
			raise e
			
		for section in rulesets:
			log('\n' + section['name'])
			items.append( [ section['name'], section['name'], False ])
	
	return items

# Populate list of rules. (rules_file is a HistoryDatasetAssociation)
# rule_sections qualifier unused at moment
def get_rule_list():

	global rulesets
	log( "\nget_rule_list() ")
	
	items = []

	for section in rulesets:
		section_name = section['name']
		for (ptr2, rule) in enumerate(section['rules']):
			if len(rule) and rule[0] != 'note':
			
				try:
					ruleString = section_name + ': ' + str(ptr2) + ': ' + ruleFormat(rule)
					# Any html tag ends need replacing, and limit thing to 100 characters.
					# ruleString = ruleString.replace('<','&lt;').replace('>','&gt;')
					ruleString = ruleString[:140] # cap it at 140 characters.
					if len(ruleString) == 140: ruleString = ruleString + '...'
					items.append( [ ruleString, section_name + ":" + str(ptr2), False ])	

				except Exception,e: 
					log("\nError: " + str(e) + '\n Rule: ' + str(rule) )

	return items

def ruleFormat(rule):
	global rc_functions
	
	midlings = []
	if len(rule) == 0: return ''

	if  hasattr(rule, '__iter__'):

		for term in rule:
			log('\nTerm ' + str(term))
			if isinstance(term, list): #Recursive call
				midlings.append(ruleFormat(term))
			else:
				if not isinstance(term, basestring):
					term = str(term ) #Ensures numeric or boolean term converted here; otherwise can't do "c in term"

				# We have to put quotes around a string term if it has %, space or double quote in it:
				if any(c in '% "' for c in term): # <>
					term =  '"'+term+'"'
					
				midlings.append(term)

		#If first item is interpretable as a function, return it with parameters bracketed,
		if midlings[0] in rc_functions:
			return midlings[0]+ '( ' + ' '.join(midlings[1:]) + ' ) ' 
		# otherwise return string straight since it may have infix() items.
		else:
			return ' ( ' + ' '.join(midlings)  + ' ) ' 

	else:
		return rule
			
	
# Populate list of available functions from python operator list as well as QC specific Iterables and NonIterables.
def get_function_list():

	global rulesets, rc_functions
	
	log( "\nget_function_list() ")
			
	RC = report_calc.ReportCalc()
	
	items = []	
	rc_functions = []
	
	# self.function definition is one step removed, so have to get function this way:
	for myMethodName in RC.functions:
		rc_functions.append(myMethodName)
		
		myMethod = RC.functions[myMethodName]
		selected = True if myMethodName == 'store' else False
		name =  myMethod.__doc__ if myMethod.__doc__ else "undocumented function()"
		items.append( [ "RC: " +  get_desc(name), myMethodName, selected])		

	for (myMethodName, myMethod) in inspect.getmembers(RCClassFnExtension, predicate=inspect.ismethod):
		if myMethodName[0:2] != "__": #Skip __init__()
			rc_functions.append(myMethodName)
			name =  myMethod.__doc__ if myMethod.__doc__ else "undocumented function()"
			items.append( [ "RC: " +  get_desc(name), myMethodName, False])		

	for (myMethodName, myMethod) in inspect.getmembers(RCStaticFnExtension, predicate=inspect.isfunction):
		rc_functions.append(myMethodName)
		name =  myMethod.__doc__ if myMethod.__doc__ else "undocumented function()"
		items.append( [ "RC: " +  get_desc(name), myMethodName, False])
		
	for (myMethodName, myMethod) in inspect.getmembers(operator, predicate=inspect.isbuiltin):
		rc_functions.append(myMethodName)
		if myMethodName[0:2] != '__': #skip underscored fns
			items.append( ["Built-in: " +get_desc(myMethod.__doc__), myMethodName, False])		

	for (myMethodName, myMethod) in inspect.getmembers(math, predicate=inspect.isbuiltin):
		rc_functions.append(myMethodName)
		if myMethodName[0:2] != '__': #skip underscored fns
			items.append( ["Built-in math: " +get_desc(myMethod.__doc__), myMethodName, False])		

	items.sort(key = lambda select: select[0])
	return items

def get_desc(desc):
	desc =  desc.strip().split('\n',1)[0]
	(bracketed, remainder) = desc.split(')',1)
	return bracketed.translate(None, ',') + ')' + remainder
	
