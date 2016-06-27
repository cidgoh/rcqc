#!/usr/bin/python
# -*- coding: utf-8 -*-

import os, sys, json, glob
import inspect
import operator
import math

# From http://code.activestate.com/recipes/66062-determining-current-function-name/
SELF_DIR = os.path.dirname(sys._getframe().f_code.co_filename)
sys.path.append(SELF_DIR)
import rcqc
from rcqc_functions.rcqc_functions import RCQCClassFnExtension
from rcqc_functions.rcqc_functions import RCQCStaticFnExtension

DEBUG =0

if DEBUG== 1:
	with open( SELF_DIR + '/log.txt', 'w') as log_handle:
		log_handle.write( "Starting ...\n")
		
sections = None
rc_functions = None

def log(message):
	if DEBUG== 1:
		with open( SELF_DIR + '/log.txt', 'a') as log_handle:
			log_handle.write(message)

def loglines(lines):
	if DEBUG== 1:
		with open( SELF_DIR + '/log.txt', 'a') as log_handle:
			log_handle.writelines(lines)
						
# Populate list of rules. (rules_file is a HistoryDatasetAssociation)
def get_rule_section(recipe_file, rules_file):

	global sections, SELF_DIR
	log( "\nget_rule_section() ")
	
	items = []

	if recipe_file: #Construct an empty class
		# See: http://jfine-python-classes.readthedocs.io/en/latest/type-name-bases-dict.html
		rules_file = type('RecipeFile',(object,),{"file_name": recipe_file})()
		log('got recipe ' + rules_file.file_name)
		
	if rules_file:
		log(rules_file.file_name)

		try:
			with open(SELF_DIR + '/' + rules_file.file_name, 'r') as rules_handle:
				rulefileobj =  json.load(rules_handle)
				log("Recipe file json parsed")
				sections = rulefileobj['sections']
				log("\nRecipe loaded")
				#loglines(sections)
				
		except Exception,e: 
			log(str(e))
			raise e
			
		for section in sections:
			log('\n' + section['name'])
			if 'type' in section and section['type'] == 'optional':
				items.append( [ section['name'], section['name'], False ])
	
	return items


def get_recipe_list():
	""" This is a list of built-in recipes, sitting in the recipes/ subfolder
	"""
	global SELF_DIR
	items = []
	for file_path in glob.glob(SELF_DIR + '/recipes/*.json'):
		with open(file_path,'r') as rules_handle:
			try:
				rulefileobj =  json.load(rules_handle)
				title =  rulefileobj['title'] if 'title' in rulefileobj else os.path.basename(file_path)
			except:
				title = 'Error: recipes/' + os.path.basename(file_path) + " is not a valid JSON formatted recipe." 

			items.append( [title, 'recipes/' + os.path.basename(file_path), False ])

	return items


# Populate list of rules. (rules_file is a HistoryDatasetAssociation)
# rule_sections qualifier unused at moment
def get_rule_list(new_option=True):

	global sections, rc_functions
	if not rc_functions:
		get_function_list()

	log( "\nget_rule_list() ")
	
	items = []

	if sections:
		for section in sections:
			section_name = section['name']
			if 'rules' in section:
				for (ptr2, rule) in enumerate(section['rules']):
					if len(rule):
			
						try:
							ruleString = section_name + ': ' + str(ptr2) + ': ' + ruleFormat(rule)
							# Any html tag ends need replacing, and limit thing to 100 characters.
							# ARCHAIC? ruleString = ruleString.replace('<','&lt;').replace('>','&gt;')
							# ruleString = ruleString[:140] # cap it at 140 characters.
							# if len(ruleString) == 140: ruleString = ruleString + '...'
							items.append( [ ruleString, section_name + ":" + str(ptr2), False ])	

						except Exception,e: 
							log("\nError: " + str(e) + '\n Rule: ' + str(rule) )

	if len(items) == 0 and new_option == True:
		section_name = 'Processing:None'
		items= [ [section_name + ' - new rule ...', section_name, True] ]
	
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
				if isinstance(term, basestring):
					if ' ' in term and term[0] != '"':
						term =  '"' + term + '"'
				else:
					term = str(term ) #Ensures numeric or boolean term converted here; otherwise can't do "c in term"
					
				midlings.append(term)
		
		print midlings
		#If first item is interpretable as a function, return it with parameters bracketed,
		if midlings[0] in rc_functions:
			return midlings[0]+ '( ' + ' '.join(midlings[1:]) + ' ) \n' 
		# otherwise return string straight since it may have infix() items.
		else:
			return ' ( ' + ' '.join(midlings)  + ' ) \n' 
		
	else:
		return rule
			
			
def quotify(content):

	for (ptr, item) in enumerate(content):
		if isinstance(item, basestring) and ' ' in item:
			content[ptr] = '"' + item + '"'

	return ' '.join(content)
	
def get_rule_variables():

	global sections
	log( "\nget_rule_variables() ")
	
	items = []

	if sections:
		for section in sections:
			if section['name'] == 'Ontology' and '@context' in section:
				for name in section['@context'].keys():
					items.append( [ name, name, False ])	

	items.sort(key=lambda x: x[1])
	
	return items


# Populate list of available functions from python operator list as well as QC specific Iterables and NonIterables.
def get_function_list():

	global sections, rc_functions
	
	log( "\nget_function_list() ")
			
	RCQC = rcqc.RCQCInterpreter()
	
	items = []	
	rc_functions = []
	
	# self.function definition is one step removed, so have to get function this way:
	for myMethodName in RCQC.functions.keys():
		rc_functions.append(myMethodName)
		
		myMethod = RCQC.functions[myMethodName]
		selected = True if myMethodName == 'store' else False
		name =  myMethod.__doc__ if myMethod.__doc__ else "undocumented function()"
		items.append( [ "rcqc: " +  get_desc(name), myMethodName, selected])		

	for (myMethodName, myMethod) in inspect.getmembers(RCQCClassFnExtension, predicate=inspect.ismethod):
		if myMethodName[0:2] != "__": #Skip __init__()
			rc_functions.append(myMethodName)
			name =  myMethod.__doc__ if myMethod.__doc__ else "undocumented function()"
			items.append( [ "rcqc: " +  get_desc(name), myMethodName, False])		

	for (myMethodName, myMethod) in inspect.getmembers(RCQCStaticFnExtension, predicate=inspect.isfunction):
		rc_functions.append(myMethodName)
		name =  myMethod.__doc__ if myMethod.__doc__ else "undocumented function()"
		items.append( [ "rcqc: " +  get_desc(name), myMethodName, False])
		
	for (myMethodName, myMethod) in inspect.getmembers(operator, predicate=inspect.isbuiltin):
		rc_functions.append(myMethodName)
		if myMethodName[0:2] != '__': #skip underscored fns
			items.append( ["built-in: " +get_desc(myMethod.__doc__), myMethodName, False])		

	for (myMethodName, myMethod) in inspect.getmembers(math, predicate=inspect.isbuiltin):
		rc_functions.append(myMethodName)
		if myMethodName[0:2] != '__': #skip underscored fns
			items.append( ["built-in math: " +get_desc(myMethod.__doc__), myMethodName, False])		

	items.sort(key = lambda select: select[0])
	return items

def get_desc(desc):
	desc =  desc.strip().split('\n',1)[0]
	(bracketed, remainder) = desc.split(')',1)
	return bracketed.translate(None, ',') + ')' + remainder
	
