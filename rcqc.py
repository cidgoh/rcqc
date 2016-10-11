#!/usr/bin/python
# -*- coding: utf-8 -*-

import datetime
import glob
import operator
import optparse
import math
import os
import pyparsing
import re
import sys
import numbers

try: #Python 2.7
	from collections import OrderedDict
except ImportError: # Python 2.6
	from ordereddict import OrderedDict
	
try:	
	import simplejson as json
except ImportError: # Python 2.6
    	import json

# These three classes, plus self.functions below, provide all of the functions available in rules to massage report data
from rcqc_functions.rcqc_functions import RCQCClassFnExtension
from rcqc_functions.rcqc_functions import RCQCStaticFnExtension

CODE_VERSION = '0.1.1'
DEBUG = 0
# 3 place infix operators e.g. "a < b" conversion to equivalent "lt(a b)" phrase.  
# Allowing all items with < and > in them to be referenced as gt lt etc.
RCQC_OPERATOR_2 = { '-':'neg', 'not':'not_' }
RCQC_OPERATOR_3 = {
	'=': '=',
	'<': 'lt', 'lt': 'lt',
	'>':'gt', 'gt':'gt',
	'>=':'ge',	'ge':'ge', 'gte':'ge',
	'==':'eq',
	'<=':'le', 'le':'le', 'lte': 'le',
	'!=':'ne', '<>':'ne', 'ne':'ne',
	'*':'mul',
	'**':'pow',
	'/':'truediv', '//':'truediv',
	'-':'sub',
	'+':'add',
	'+=':'iadd',
	'%':'mod'
} 


class MyParser(optparse.OptionParser):
	"""
	Allows formatted help info.  From http://stackoverflow.com/questions/1857346/python-optparse-how-to-include-additional-info-in-usage-output.
	"""
	def format_epilog(self, formatter):
		return self.epilog

def stop_err( msg, exit_code=1 ):
	sys.stderr.write("%s\n" % msg)
	sys.exit(exit_code)

class RCQCInterpreter(object):
	"""
	The RCQCInterpreter class 
	
	General notes:
		Most iterables yield (over and over) a dictionary containing a "value" field (usually originating from a named group regular expression of form "...<?P<name>[match expression...]>...".  Usually this includes a "DICT_ROW" key which is the row offset (or count) of the current row result since start of iterable.
	"""
	def __init__(self):

		self.version = None
		self.options = None
		self.function_stack = [] # stack of functions called, from top-level to currently executing one
		
		# namespace includes variables and rules
		self.namespace = {} # Will be hash list of input files of whatever textual content
		self.namespace['report'] = OrderedDict()
		self.namespace['report']['title'] = "RCQC Quality Control Report"			
		self.namespace['report']['tool_version'] = CODE_VERSION	
		self.namespace['report']['job'] = {'status': 'ok'}
		self.namespace['report']['quality_control'] =  {'status': 'ok'}

		self.namespace['sections'] = []
		self.namespace['rule_index'] = {} # rule index based on location of store(_, location) field. 1 per.
		self.namespace['name_index'] = {} # index based on last (z) key of x.y.z namespace reference.
		self.namespace['files'] = [] 
		self.namespace['file_names'] = {} 
		self.namespace['iterator'] = {} # Provides the dictionary for each current iterator function evaluation (at call depth). 
		self.namespace['report_html'] = ''	

		self.input_file_paths = None	
		self.ruleset_file_path = None	
		self.output_json_file = None	

		# Really core functions below require access to RCQC class variables.  
		# Other functions can be added in rcqc_functions RCQCClassFnExtension and RCQCStaticFnExtension classes.
		self.functions = {
			'=': lambda location, value: self.storeNamespaceValue(value, location),
			'store': self.storeNamespaceValue, 
			'store_array': self.storeNamespaceValueAsArray,
			'if': self.fnIf,
			'fail': self.fail,
			'exit': self.exit,
			'exists': lambda location: self.namespaceReadValue(location, True),
			'-': lambda x: operator.neg(x),
			'not': lambda x: operator.not_(x),
			'function': lambda x: self.applyRules(x)
		}
		
	
	def __main__(self):
		"""
		Applies the interpreter to given rules file and command-line data.
		
		Currently it triggers these exit code signals:
		 - exit code 1 to fail this Repor Calc app job (leads to failure of complete workflow pipeline job).
		 - exit code 2 to request a retry of tool job (if workflow engine supports this).  Automatic retry limit not yet implemented.
		 
		FUTURE: enable RCQC to provide more detail to the workflow engine about what to retry.
		""" 
		global DEBUG
		options, args = self.get_command_line()
		self.options = options
		
		if options.debug:
			DEBUG = 1	

		_nowabout = datetime.datetime.utcnow() 
		#self.dateTime = long(_nowabout.strftime("%s"))
		start_time =  _nowabout.strftime('%Y-%m-%d %H:%M')
		self.namespace['report']['date'] = start_time
		print "Generating RCQC report ... " + start_time
		
		if options.code_version:
			print CODE_VERSION
			return CODE_VERSION
			
		if options.daisychain_file_path:
			with open(options.daisychain_file_path, 'r') as daisychain_handle:
				self.namespace['report'] = json.load(daisychain_handle, object_pairs_hook=OrderedDict)
				# Nicknames need to be established! # I.e. every dictionary key in report namespace
				# An existing report may have several sequence sections; this nickname system will only point to last in (ordered!? list).
				for item in self.namespace['report']:
					self.setNicknames(item, self.namespace['report'])
				 
		#NOTE: This flat list of settings are overwritten by any such settings the recipe script establishes.
		if options.json_object:
			json_data =  json.loads(options.json_object, object_pairs_hook=OrderedDict ) #OrderedDict preserves order.
			for item in json_data:
				# Issue: subsequent programming can rely on nicknames, so each variable read in needs 
				# to be entered with store().
				self.namespace[item] = {}
				for item2 in json_data[item]:
					self.storeNamespaceValue(self.getAtomicType(json_data[item][item2]) , item + '/' + item2)

		if options.output_html_file: 
			self.output_html_file = options.output_html_file 	#-H [file]
		self.output_folder = options.output_folder if options.output_folder else os.getcwd() #-f [folder]
		if options.input_file_paths: 
			self.input_file_paths = options.input_file_paths.strip()	#-i [string]

		self.optional_sections = map(str.strip, options.optional_sections.strip().strip(",").split(",") ) #cleanup list of execute section(s)

		# ************ MAIN CONTROL ***************
		self.getRules()
		
		if self.input_file_paths:
			self.getInputFiles()
			
		execute_sections = []		
		for item in self.namespace['sections']:
			if not 'type' in item or (item['type'] == 'optional' and item['name'] in self.optional_sections):
				print "Executing: " , item['name'] 
				self.applyRules(item['name'])

		mytimedelta = datetime.datetime.utcnow() -_nowabout
		print "Completed in %d.%d seconds." % (mytimedelta.seconds, mytimedelta.microseconds)

		self.exit()


	def exit(self, exit_code = 0, message = ''):
		"""
		exit(exit_code = 0) -- Stops processing ruleset immediately and exits with given code.  It will finish composing and saving report files first.
		"""
		location = 'job'
		
		if self.options.output_json_file:
			self.writeJSONReport(self.options.output_json_file)		
		if self.options.output_html_file:
			self.writeHTMLReport('Report Summary')
			
		if exit_code == 1:
			self.storeNamespaceValue("FAIL", 'report/job/status')
		if exit_code == 2:
			self.storeNamespaceValue("RETRY",  'report/job/status')
		
		# Failure trigger if report/job/status == "FAIL"
		status = self.namespace['report']['job']['status'].lower()
		if status == 'fail':
			exit_code = 1
			message = 'This job quality report triggered a workflow fail signal!'
		elif status == 'retry':
			exit_code = 2
			message = 'This job quality report triggered a workflow retry signal!'

		self.messageAppend(message, location)					
		stop_err(message, exit_code)

	
	def fail(self, location = 'job', message = ''):
		"""
		fail(location=report/job, message='') -- sets value of location/status to "FAIL" (and continues rule processing) .  Short for store(FAIL, location).  Adds optional message.  If location is report/job, this will fail it.
		"""
		if location != 'job':
			location = 'quality_control'
			
		self.storeNamespaceValue("FAIL",'report/%s/status' % location)
		self.messageAppend(message, location)
			
			
	def messageAppend(self, message=None, location='job'):
		"""
		given message is appended to list of exit/fail messages.  By default in report/job/message, but could be quality_control/ too.
		"""
		if message:	
			if not 'message' in self.namespace['report'][location]:	
				self.namespace['report'][location]['message'] = []

			message = self.namespaceSearchReplace(message)  # could even be a variable?	
			self.namespace['report'][location]['message'].append(message)
			
			
	def applyRules(self, section_name):
		"""
		Now apply each rule.  A rule consists of one or more functions followed by parameters.
		NOTE: Ordering of execute_sections doesn't matter.  Execution order depends on sections order.
		"""
		section = next((x for x in self.namespace['sections'] if x['name'] == section_name), None)
		if DEBUG > 0: print section
				
		if 'rules' in section:
			for (row, myRule) in enumerate(section['rules']):
				self.rule_row = row
				self.evaluateFn(list(myRule)) # Whatever rules might return isn't used.


	def evaluateFn(self, myList):
		"""
		Implements a Polish / Prefix notation parser.  It doesn't test arity of functions
		Lookup termStr, which should be a built-in function (or maybe a namespace reference to a function?)
		If no function is found, parameters are not evaluated.
		
		For now all in-place functions can have only 2 arguments, and they can't handle LISTS / DICTIONARIES / ITERATION
		Operator.inplace functions like iconcat() won't change the 1st parameter's value if it is immutable (string, number, tuple).  "inplace" below will only change value if it is a list or dictionary.
		"""
		
		if DEBUG > 0: print "EVALUATING: " , myList
		
		term = myList[0] 
		if not term:
			print 'A funtion expression is empty in rule #' + str(self.rule_row)			
			return
		
		if isinstance(term, basestring):
			aFunction = self.matchFunction(term)
			if aFunction:
				return self.executeFunction(aFunction, myList)

		elif isinstance(term, list): #This may be a list of functions
			return self.executeFunction(self.matchFunction("all"), ["all"] + myList) #so myList 1st param run too.
		
		# Nothing to evaluate, so just return this verbatim.
		print "RETURNING (no function): ", myList
		return myList
		

	def executeFunction(self, childFn, myList):
	
		result = None
		self.function_stack.append(childFn) #Save so subordinate functions have access to their caller
		# Parameter is a function so evaluate it.  Could get a constant , dict or iterable back.
		#if True:
		try:

			fnObj = self.evaluateParams( childFn, myList[1:])

			# Finally execute function on arguments.	
			if DEBUG > 0: print 'Executing function:', fnObj['name'], fnObj['args']			
			if childFn['static'] == True: 
				result = fnObj['fn'](*fnObj['args'])
					
				if childFn['inplace'] == True:
					# If this is an in-place function, it means we need to take function's returned value and place it in 1st parameter's textual value namespace.  
					# arg[0] may be set to namespace value, for function to process.
					# fnObj['argText'][0] is textual name of first variable that was recognized already, where inplace results are tob e stored.
					# Mainly, 1st variable needs to remain a textual location. All inplace functions should RETURN their value for substitution this way.		
					# result = fnObj['fn'](inplace, fnObj['args'][1]) #doesn't work
					self.storeNamespaceValue(result, fnObj['argText'][0], False)
				
			else: # These functions need access to Report Calc instance's namespace or functions:
				myobj = RCQCClassFnExtension(self)
				result = fnObj['fn'](* ([myobj] + fnObj['args']) )
				
			if DEBUG > 0: print "Result: ", result

		#An "iterator is not subscriptable" error will occur if program tries to reference namespace/iterator/x where x doesn't exist.
		# Error handling notes:https://doughellmann.com/blog/2009/06/19/python-exception-handling-techniques/
			#"""
		except AttributeError as e: result = None; self.ruleError(e)
		except TypeError as e: result = None; self.ruleError(e)
		except IOError as e: 
			print "I/O error({0}): {1}".format(e.errno, e.strerror); self.ruleError(e)
		except OSError as e: result = None; self.ruleError(e)
		except ValueError as e: result = None; self.ruleError(e)	
		except KeyError as e: result = None; self.ruleError(e)
		# ISSUE: if code mentions function without "self." prefix, generates a name error and freezes.  WHY?  Also, fn call with wrong # parameters yeids typeError and freezes.  Basically all runtime compilation related errors freeze code, while non-compilation ones generate an error log as desired.			
		except NameError as e: result = None; self.ruleError(e)

		except SystemExit as e: result = None; sys.tracebacklimit = 0
			
		except Exception as e: # includes  SystemExit
			self.ruleError(e)
			stop_err( 'Halting program' )
		
		finally: 
			#"""					
			self.function_stack.pop()
			return result

		
	def ruleError(self, e):
		if len(self.function_stack):
			ruleObj = self.function_stack[-1]
			if len(ruleObj['argText']) > 0:
				args = '"' + '", "'.join(ruleObj['argText']) + '"' # guarantees any numeric params will be displayed too
			else:
				args = ''
			fn_name = ruleObj['name']
		else:
			args = ''
			fn_name = ''
	 	print 'Rule #%s: %s(%s) \nproblem %s : %s ' % ( self.rule_row, fn_name, args, type(e), str(e))
	 	return None



	def evaluateAuxFunctions(self, auxFunctions):
		"""
		for store(), auxiliary functions get to operate within same iterable as set operation.
		No attention is paid to returned results.
		None of the parameters have been evaluated.
		"""
		for myFn in auxFunctions:
			if myFn and isinstance(myFn, list): 
				if DEBUG > 0: print "EVALUATING AUX Function: ", myFn
				self.evaluateFn(myFn) 	


	def evaluateParams(self, ruleObj, parameterList = None):
		"""
		Evaluate each argument/parameter of function, subject to any meta rules about term evaluation.
		"""
		# Should move this to rule parser 2nd pass. (After rules are saved to file option)
		skipEval = False
		parameterCount = 0
			
		# Loop on parameterList processing, allowing for fns that have no params
		while True: 
			argCt = len(ruleObj['args'])
			functionName = ruleObj['name']
			if  argCt < ruleObj['argcount']:
				if  len(parameterList) ==  0:
					function_spec = ruleObj['fn'].__doc__.strip().split('\n',1)[0]
					optionals = function_spec.split('--',1)[0].count('=') # indicates optional parameters in definition
					if argCt <  ruleObj['argcount'] - optionals:
						raise ValueError ('A rule expression needs arguments in rule #' + str(self.rule_row) + ".  \nSee: " + function_spec)
			
			if argCt >= 1:

				# For some functions, when first arg is loaded, its truth is evaluated, determining if remaining args are skipped.
				if functionName in ['if','iif']: 

					param1 = ruleObj['args'][0]
			
					if not isinstance (param1, bool):
						stop_err('Error: the %s() command conditional in rule #%s was not a boolean: %s %s' % (functionName, self.rule_row, param1, type(param1) ) )
						
					# The  true expression is evaluated if conditional was true.
					if argCt == 1:
						skipEval = not param1

					# "iif" also has 3rd etc. arguments which are evaluated if conditional was false.
					elif argCt == 2  and functionName == 'iif':
						skipEval = param1 # Proceed to evaluate 3rd etc argument.

				elif functionName in ['getitem', 'iterate']: 
					skipEval = True
			
			elif functionName in [ 'note', 'function']: 
				skipEval = True
				
			# Process another parameter if any			
			if len(parameterList):
				
				termStr = parameterList.pop(0)
				result = termStr
				parameterCount += 1
				
				if skipEval == False:
					# Bracketed expression terms are usually functions that need to be evaluated.
					# One issue: don't try to use bracketed items like an array if items can be confused with function names
					if isinstance(termStr, list):
						result = self.evaluateFn(termStr)	
						# Items in termStr can sometimes be prefix notation arrays like [[[a / b] * 2] - 5 ]
						filling =  '...' if len(ruleObj['argText']) == 0 else ', '.join( ruleObj['argText'] )
						termStr = str(termStr[0]) + '( ' + filling + ' )'  # For debuging
						
					elif isinstance(termStr, basestring): #might be a number or boolean.
	  					
	  					# If parameter is quoted, pass it back as is. It is never looked up against namespace.
	  					if len(termStr) and termStr[0] == termStr[-1] == '"':
		  					result = termStr[1:-1]

	  					# When store(value location ...) called, location gets s&r with possible %(...) pattern.
	  					elif (functionName in ['store'] and parameterCount==2) \
  							or ( (functionName in ['=','exists']) and parameterCount==1): # ruleObj['inplace'] == True or 
  							#For a 'store' operation we never want the value of the target variable. 
  							termStr = self.namespaceSearchReplace(termStr, True)
  							result = termStr
  						else:
  							# Try parameter match to a namespace variable's value
							# If no match found, it just returns given string.
							termStr = self.namespaceSearchReplace(termStr) # CRITICAL for 
							result = self.namespaceReadValue(termStr)
	
	  					# Do we need a de() delayed execution function 
	  					# to preserve quotes for some functions to process?

				# After adding new argument to current rule, re-evaluate it with respect to queue ...	
				ruleObj['args'].append(result)
				ruleObj['argText'].append( str(termStr) )
			
			# When all parameters have been analyzed, return the function object.
			if len(parameterList) == 0:
				return ruleObj
		
		
	def matchFunction(self, termStr):
		"""
		Attempts to locate given term string to list of various function names in operator 
		and math library and in RCQC's own Iterable and Noniterable function lists.
		SEE ALSO: report_calc_form.py get_function_list()
		"""
		static = True
		inplace = False
		if hasattr(operator, termStr) or hasattr(math, termStr): # Utilize built-in python operators
			if hasattr(operator, termStr):
				ruleFn = getattr(operator, termStr)
			else:
				ruleFn = getattr(math, termStr)
			fnDef = ruleFn.__doc__ # Only way to determine number of parameters is to pick apart definition doc.
			argcount = fnDef[ fnDef.index(termStr+'(')+len(termStr) : fnDef.index(')') ].count(',')+1 
			
			if termStr in ['iconcat','iadd','iand','idiv','ifloordiv','ilshift','imod','imul','ior','ipow','irepeat','irshift','isub','itruediv','ixor']:
				inplace = True
				
		elif termStr in self.functions:
			ruleFn =  self.functions[termStr]
			# Self.functions operate within RCQC object environment, so have "self" as first arg, so we dec arg count.
			argcount = ruleFn.func_code.co_argcount-1
									
		# These Guys get passed "self" so they have access to active namespace.
		elif hasattr(RCQCClassFnExtension, termStr):
			ruleFn = getattr(RCQCClassFnExtension, termStr)
			argcount = ruleFn.func_code.co_argcount
			static = False
			if termStr in ['clear','iStatBP']:
				inplace = True

		elif hasattr(RCQCStaticFnExtension, termStr): 		
			ruleFn = getattr(RCQCStaticFnExtension, termStr)
			argcount = ruleFn.func_code.co_argcount
			
		else: 	# Not recognized as a function.  
			return False

		return {
			'fn': ruleFn, 
			'static': static,
			'inplace': inplace,
			'name' : termStr,
			'argcount' : argcount, # Number of args as indicated in function documentation, includes optional
			'args':[],
			'argText':[]
		}


	def fnIf(self, conditional, *auxFunctions): # can't call it "if" - generates syntax error.
		"""
		if (conditional, consequent ...) -- If conditional evaluates to True, evaluate consequent
		Up in evaluateParams() conditional has already been tested and appropraite consequent has already been executed!
		ALTERNATELY: could disable evaluateParameters for "if" and instead do them here		
		using "self.evaluateAuxFunctions(auxFunctions)" ?
		"""
		return conditional

 		
	def storeNamespaceValue(self, valueObj, location, *auxFunctions):
		"""
		store (expression, location ...) -- Evaluate expression and set namespace location to it.  
		"""
		self.setNamespace(valueObj, location, False, auxFunctions)
	
	
	def storeNamespaceValueAsArray(self, value, location, *auxFunctions):
		"""
		storeArray (value, location ...) -- Value is converted into an array if it isn't already, then stored in namespace location.
		"""
		self.setNamespace(value, location, True, auxFunctions)
		
		
	def setNamespace(self, valueObj, location, asArray, auxFunctions):
		"""
		setNamespace (value, location, asArray=False, auxilliary functions)
		Case: 
			(Location is a function: it will already have been evaluated into a string by this point.)
			Location is a string:
				Location is an existing namespace reference: that is used as storage location

				Location contains one or more variable {name} indicators.
					If the {name} location resolves to a namespace location, then do conversion.
					Otherwise 
				
		Location needs to be a raw string of x/y/z format so we can use getNamespace() on it to 
		 return object = x/y and key = z.  If location had been evaluated as "store" fn parameters were
		 gathered, and it had already taken a value, we'd have nonsense of trying to set one value to another.  
		
		B) if valueObj is an iterator - or chain of iterators, they'll actually generate results one by one below.
		
		ISSUE: A list of items that are not dictionaries can be presented.  Should be a different case from iterable?
				
		"""

		fnDepth = str(len(self.function_stack)-1)
		self.namespace['iterator'][fnDepth] = None
					
		#Note: for "a/b/c", this creates a dictionary obj called "b" at "a/b" if it doesn't exist already.
		(obj, key) = self.getNamespace(location) 

		# This catches case where valueObj is not an iterable.  It is a simple string, number, or boolean.
		if not (hasattr(valueObj, '__iter__')): #  or isinstance( valueObj, (dict, list) ) 
			if DEBUG > 0: "store(%s, %s)" % (valueObj, location)		
			obj[key] = valueObj
			self.evaluateAuxFunctions(auxFunctions)
			return True
		
		# Handle iterable functions from here on.
		found = False
		if '%(' in key: 
			# Each iterator row result is saved as separate location/key when
			# location contains {name} parameter to vary each row.
			# substitution can work on any other named parameters as long as they
			# are defined in dictionary (e.g. by regex named group search).
 			for myDict in valueObj:
				found = True
				try: # Run name through search and replace if any '%(foo)s' in it.
					finalKey = location % myDict  # >= Python 2.6 
				except KeyError:
					raise KeyError ('Unable to match location term "%s" in dictionary %s:' % (location, str(myDict)) )
					
				if DEBUG > 0: print "Set separate rows (%s) %s = %s" % (location, key ,valueObj)
				(obj, key) = self.getNamespace(finalKey)			
				obj[key] = myDict['value']
				self.namespace['iterator'][fnDepth] = myDict
				self.evaluateAuxFunctions(auxFunctions)
		
		# Here we have a dictionary or list or iterable.
		# Save all rows as array to single entry.  Note, final location doesn't see iterations?
		elif isinstance( valueObj, (dict,list) ) :
			obj[key] = valueObj
			found = True
		else:
		#if True:
			myResultArray = [] 

			for myDict in valueObj: 
				found = True
				self.namespace['iterator'][fnDepth] = myDict #fnDepth needs to be string, not int?
				#print 'Iteration single array dict at depth:', fnDepth, self.namespace['iterator'][fnDepth]
				self.evaluateAuxFunctions(auxFunctions)
				if 'value' in myDict:
					myResultArray.append(myDict['value'])
				else: #source no longer has 'value' if it is a copy from some other data structure in namespace
					raise ValueError ('store() needs given dictionary to have a \'value\' key.  If derived from a regular expression search, did it have a "(?P<value>...)" named group?')
				
			if asArray==True or len(myResultArray) > 1:
				obj[key] = myResultArray
			elif len(myResultArray) == 1: 
				obj[key] = myResultArray[0]

			#if DEBUG > 0: print "Set single entry (%s) /%s" % (location, key)


		# There is no way to see if an iterable has content without starting to execute it.  So we have to check  for emptiness via a flag.
		if not found: 
			obj[key] = None
			print "No results, can't set (%s) " % location
			return False		
		
		return True


	def namespaceSearchReplace(self, location, convert=False):
		"""
		convert=True: causes {name} expression to be converted to python %(name)s expression if {name} not found in namespace.  Means it was meant for narrower iterator dictionary search and replace scope.
		Check case where string substitutions "a/b{name}/c" point to namespace locations.
		Note: this might conflict with dictionary terms.  It is up to programmer to avoid namespace vs dictionary term confusion (e.g. "value" or "name" used as variables and dictionary keys).  Or we add distinguishing mark for dictionary lookup.

		INPUT
		location: string
		
		RETURNS
			string
		"""

		if not isinstance(location, basestring):
			return location

		ptr = 0
		while True:
			startPtr = location.find('{', ptr)
			if startPtr == -1: break;
			endPtr = location.find('}', startPtr+1)
			if endPtr == -1: break;
		
			reference = location[startPtr+1 : endPtr]
			newReference = self.namespaceReadValue(reference)
			#Allow strings and numbers to be substituted in
			if isinstance(newReference, numbers.Number):
				newReference = str(newReference) 
				
			if isinstance(newReference, basestring):
				if reference == newReference and convert == True:
					# If no change in value then it wasn't recognized in namespace.
					# So convert it to dictionary lookup %([phrase])s instead.
					newReference = '%(' + reference + ')s'
				
				location = location[:startPtr] + newReference + location[endPtr +1:]

				ptr = startPtr+len(newReference)
			else:
				ptr = endPtr 
	
		return location


	def getRules(self):
		
		if self.options.recipe_file_path and self.options.recipe_file_path != 'None':
			self.recipe_file_path = self.options.recipe_file_path
			if self.recipe_file_path[0] != '/': # Get absolute path if relative path provided.  Expecting 'recipes/[recipe_name]'
				self.recipe_file_path = self.getSelfDir() + '/' + self.recipe_file_path
				
			if not os.path.exists(self.recipe_file_path):
			 	stop_err('Unable to locate the recipe file! \nRecipe file: %s' % self.recipe_file_path )
			 	
			with open(self.recipe_file_path,'r') as rules_handle:
				rulefileobj =  json.load(rules_handle, object_pairs_hook=OrderedDict)
		else:
			# Provides a default empty ruleset to add customized rules to.
			rulefileobj = {
				'sections':[{
					'name': 'Processing',
					'rules': []
				}]
			}
			self.optional_sections = ['Processing']
			
		self.namespace['sections'] = rulefileobj['sections']

		if self.options.custom_rules:
			# options.custom_rules is a short-lived file, existing only so long as tool is executing.
			# The Galaxy tool <configfile> tag writes this content directly as json data.
			#with open(self.options.custom_rules,'r') as rules_handle: print  rules_handle.read()
			
			with open(self.options.custom_rules,'r') as rules_handle:
				lines = rules_handle.readlines()
			
			self.custom_rules = []
			for line in lines:
				linesplit = line.strip().split('\t',2) # remaining tabs are within rule content
				if len(linesplit) == 3:
					(row,drop,rules) = linesplit 
					self.custom_rules.append({
						'row':row,
						'drop': 0 if drop == 'False' else int(drop),
						'rules': rules.decode('base64')
					})
					#print self.custom_rules[-1]
			
			# Using this to convert "f1 (a f2 (c d))" into python nested array [f1 [a,  f2 [c, d]]]
			# Could be improved to handle dissemble() fn too.
			bracketed_rule = pyparsing.nestedExpr() 
			
			# Now sort these in reverse by rule row, so when processing rules we don't mess up ins/del positions.
			# Each row now begins with section name, so have to get past ":"
			self.custom_rules.sort(key = lambda x: x['row'].split(':')[0]+x['row'].split(':')[1].zfill(5) if x['row']!= 'None' else 'zzz999', reverse=True)
			
			for rule_group in self.custom_rules: 
				rule_section = None
				
				# Add row to processing section.
				if rule_group['row'] == 'None':
					if len(rule_group['rules']) > 0 or rule_group['drop'] > 0:
						stop_err('To add/drop rules, please specify a rule-section using "+ At rule" option. ')
					else:
						stop_err('An empty "Customize" section was specified.  Please populate or remove this section')
			
				section, row = rule_group['row'].split(":") #Contains section and row of rule to modify.
				row =  row.strip() # Can be "None"
				
				for ruleset in self.namespace['sections']:
					if ruleset['name'] == section:
						rule_section = ruleset['rules']
				if rule_section == None:
					stop_err('Unable to find rule section "%s" for custom rule # %s' % (section , row) )

				try:
					parsed_ruleset = bracketed_rule.parseString('(' +rule_group['rules'] + ')').asList()[0]
				except pyparsing.ParseException as e:
					stop_err( "Parsing problem in ruleset %s :" % row, e)
			
				parsed_rules = self.dissemble(parsed_ruleset)

				for ptr2, parsed_rule in enumerate(parsed_rules):
					if row == 'None' or row == None or row == '': #If no row given, append rule.
						rule_section.append(parsed_rule)
						print 'Appended new rule in %s : %s ' % (section, parsed_rule)
					else: # Insert rule in right spot in report's rulebase. 
						rule_section.insert(int(row)+ptr2+1, parsed_rule)
						print 'Inserted new rule in %s: %s ' % (section, parsed_rule)

				# Now drop any rules (working from highest row rule mod to lowest).
				if rule_group['drop'] > 0:
					if row == "None":
						stop_err('In order to delete a number of rules, one must select starting rule row using "At rule" input.')			
					print "Dropping ", row, rule_group['drop']		
					del rule_section[int(row) : int(row) + rule_group['drop']]
							
				# Build crude rule index for easy reference in report (i.e. set Z because of rule X,Y).
				for (ptr, rule) in enumerate(rule_section):
					if rule[0] =='store':
						if len(rule) > 2 and isinstance(rule[2], basestring): 
							if rule[2] in self.namespace['rule_index']:
								self.namespace['rule_index'][rule[2]].append(rule)
						 	else:
						 		self.namespace['rule_index'][rule[2]] = [rule] # 2 = location param
						else:
							raise ValueError ("Rule # %s has a store() command with insufficient or malformed parameters" % ptr)


		if self.options.save_rules_path:
			# Only the sections part of a rulefile object can change; the other attributes are copied from ruleset file.
			rulefileobj['sections'] = self.namespace['sections'] 
			with (open(self.options.save_rules_path,'w')) as output_handle:
				output_handle.write(json.dumps(rulefileobj,  sort_keys=True, indent=4, separators=(',', ': ')))

		# Now, since they're saved, go back over rules and convert any infix expressions to prefix
		for rule_section in self.namespace['sections']:
			if 'rules' in rule_section:
				for (ptr, rule) in enumerate(rule_section['rules']):
					rule_section['rules'][ptr] = self.infixToPrefix(rule)

	def infixToPrefix(self, rule): # given rule is always an array
		"""
		Revises any rule so that any [a fn b] is rewritten [fn a b] , recursively.
		No operator precedence except by left to right evaluation.
		"""
		if not isinstance(rule, list): return rule
		
		ptr = 0
		while ptr < len(rule):
			term = rule[ptr]
			if isinstance(term, list ): 
				rule[ptr] = self.infixToPrefix(term)
				term = rule[ptr]

			# [op a ...] => [ [op a] ...]
			if isinstance(term, basestring) and term in RCQC_OPERATOR_2 and ptr < len(rule) - 1:
				rule[ptr] = [ RCQC_OPERATOR_2[term], self.infixToPrefix( rule[ptr + 1] ) ]
				del rule[ptr+1]
			
			# [a op b ...] => [ [op a b] ... ]  .  Note syntax error if "a" is an op too.
			if ptr < len(rule) - 2:
				term1 = rule[ptr+1]
				if isinstance(term1, basestring) and term1 in RCQC_OPERATOR_3:
					rule[ptr] = [ RCQC_OPERATOR_3[ term1], self.infixToPrefix( rule[ptr] ),  self.infixToPrefix( rule[ptr+2] ) ]
					del rule[ptr+1: ptr+3]
				
			ptr += 1
			
			while len(rule) == 1 and isinstance(rule[0], list ):  # Simplify ((...)) => (...)
				rule = rule[0]
		return rule
		
		
	def dissemble(self, myList):
		"""
			Do parse of incomming bracketed f1 (a f2 (c d))) expressions.
			Parser actually has already converted these to array structure: [f1 [a,  f2 [c d]]]
			Dissemble these into prefix style [f1, a, [f2 c d]] structure
			Note: this isn't double checking that function name is valid, nor does it check for correct # params.
			Problem case?: if inner infix notation function "fn ((a < fn (b c)) ... )" exists, "fn (b c)" won't get converted to "(fn b c)" ?
		"""
		if isinstance(myList, list):
			ptr = 0
			while ptr < len(myList): 
				item = myList[ptr]
				if DEBUG: print item, type(item)
				# CURRENTLY all incomming items are of type unicode rather than simply basestring
				if isinstance(item, (basestring, unicode)):
					item = self.getAtomicType(item)
				else:
					for (itemPtr, flatItem) in enumerate(item):
						item[itemPtr] = self.getAtomicType(flatItem)
						
				if ptr < len(myList) -1 and  isinstance(myList[ptr+1], list): # at least one more term to go
					if DEBUG: print "Disassembling", myList[ptr+1], len(myList[ptr+1])
					myList[ptr] = [item] + self.dissemble(myList[ptr+1])
					del myList[ptr+1]
				else:
					myList[ptr] = item
				ptr = ptr + 1

		return myList

	def getAtomicType(self, item):
		# All items having quotes are taken as literal strings
		if len(item) > 0 and item[0] == '"' and item[-1] == '"': # Drop quotes around term; it remains a string.
			pass
		else: # See if term should be converted to number / boolean
			item = RCQCStaticFnExtension.parseDataType(item)

		return item
						

	def getInputFiles(self):
		"""
		Place each input file's basic information into an array in self.namespace['files'] namespace.  Each row contains a dictionary (object) having file_name, file_path, and file_type properties.

		@uses self.input_file_paths: A string interpretable as a space-separated array of file data, each of which has 3 parts:
		1) full Galaxy file path, 
		2) label for file that rules can use to reference it.  Label should not contain spaces.
		3) file type
		"""	
		# whitespace separated file items:
		for item in self.input_file_paths.strip().split(","): 

			(file_path, file_name, file_type) = item.strip().split(":")
			fileObj = {
				'name': file_name,
				'value': file_path,
				'type': file_type
			}
			self.namespace['files'].append(fileObj )
			self.namespace['file_names'][file_name] = fileObj


	def writeHTMLReport(self, title):
		try:
			with (open(self.output_html_file, 'w')) as output_handle:
				self.namespace['report_html'] = "<p>Output folder: %s</p>\n\n%s" % (self.output_folder, self.namespace['report_html'] )
				output_handle.write(RCQCStaticFnExtension.pageHtml (self.namespace['report_html'], title) )

		except IOError as e: 
			print "IO error(%s): %s when trying to write %s" % (e.errno, e.strerror, self.output_html_file)
			raise e


	def writeJSONReport(self, output_json_file=None):
		"""
		writeReport(output_json_file=None)
		Write out report file - i.e. anything within namespace['report']
		default=lambda: "[nasty iterable]" provides warning string for any objects left in report at this stage.  Shouldn't be any.
		
		We don't sort the keys because some dictionaries are ORDERED for display, and others aren't.
		"""
		report = json.dumps(self.namespace['report'], sort_keys=False, indent=4, separators=(',', ': '), default=lambda: "[nasty iterable]")
		try:
			with (open(output_json_file,'w') if output_json_file else sys.stdout) as output_handle:
				output_handle.write(report)
		except OSError as e: 
			print "OS error(%s): %s when trying to write %s" % (e.errno, e.strerror, self.output_html_file)
			raise e


	def getNamespace(self, myName):
		"""
		Search self.namespace for appropriate path, and create it if necessary.  Used by store(...,location), 
		"""
		if not isinstance(myName, basestring):
			raise TypeError ("Problem: getNamespace() given a non-string argument for location:", myName, type(myName) )
		
		# Retrieval of shortcut variable name .z when original name is x.y.z		
		if myName[0] == '/':
			print ('ALERT: "%s" not matched to namespace so it is now a string constant.  Perhaps it didn\'t get set?' % myName)
			return myName
		
		focus = self.namespace
		splitName = myName.split('/')
		ptrNextLast = len(splitName)-1
		for (ptr, part) in enumerate(splitName):
			if not isinstance(focus, dict):
				raise TypeError('The namespace path "%s" doesn\'t point to a dictionary.  Was it previously set to a constant?' % '/'.join(splitName[0:ptr]) )
				
			if not part in focus:
			
				# If first item is a nickname, start search from there.
				if ptr == 0:
					(parent, returnable) = self.getNickname(part, True)
					if returnable:
						focus = parent
			
			if part in focus:
			
				# Every part of path except for root child is given a nickname if it hasn't been seen before (if it isnt a number or %(xxx) expression
				if ptr > 0 and not part in self.namespace['name_index']:
					self.setNickname(focus, part)
			
				# At y in ...x/y/z path:
				if ptr == ptrNextLast:
					return (focus, part)
				
				focus = focus[part]
				continue
				 
			# At y in ...x/y/z path:
			if ptr == ptrNextLast:
				self.setNickname(focus, part)
				return (focus, part)
			
			#Not at last place in path, so create a dictionary item for part
			focus[part] = OrderedDict() #Its left to other iterators to set up arrays.
			self.setNickname(focus, part)

			# Advance along path
			focus = focus[part] 	
		

	def namespaceReadValue(self, myName, existsFlag = False):
		"""
		Attempts to find value in appropriate path, and return that object or value;
		if part "b" in "a/b/c" is numeric, will check to see if "a" is an array. 
		If whole path is not found, will return myName as a literal.
		Assumes all a/b{name}/c substitutions have already been done.
		Means top level variables superceed any previous nicknames established via leaf store()
		Abbreviations are checked for top-level match before bottom-level match.
		If existFlag == True, return whether or not given variable exists.
		"""
		if not isinstance(myName, basestring) or len(myName) == 0 or myName[0] == '/' or ' ' in myName:
			return myName
				
		splitName = myName.split('/')
		focus = self.namespace	

		#Here we have a path with slashes
		for (ptr, part) in enumerate(splitName):
		
			if focus != None:
				if isinstance(focus, dict):
					if part in focus:
						focus = focus[part] # Advance along path
						continue
					#If first term is nickname, see if we can pick up path from it
					if ptr == 0:
						(reference, returnable) = self.getNickname(part)
						if returnable:
							focus = reference
							continue

				if isinstance(focus, list):
					if part.isnumeric():
						partint = int(part)
						if partint >= 0 and partint < len(focus):
							focus = focus[partint]
							continue

					if existsFlag: return False					
					raise TypeError('The location namespace path "%s" is a list, but it doesn\'t have position "%s" !' % ('/'.join(splitName[0:ptr]), part) )
			
			if existsFlag: return False
			return myName # Term is a literal 

		if existsFlag: return True
		return focus # now a value / object
	
	
	def getNickname(self, nickname, parent_flag=False):
		""" 
		Whenever the "store(... location)" function is called, a reverse lookup is set up on the leaf c part of the location's a/b/c path to point to the full path.  Thus c can be a nickname to the latest use of the term.  The only issue arises if c is overwritten by other processes that happen to store paths with the same c leaf. In such cases programmers must change rule references to a leaf name, or stick to the full path a/b/c reference for that variable.
		INPUT
		parent_flag: boolean indicating that parent dict is desired.
		"""
		if nickname in self.namespace['name_index']: #find shortcut "myname" type variable references
			parentDict = self.namespace['name_index'][nickname]
			if DEBUG: print 'Found "/%s"' % nickname
			# Verify, since sometimes something can change nickname's entry/ data structure path
			if nickname in parentDict:
				if parent_flag == False:
					return (parentDict[nickname], True)
				else:
					return (parentDict, True)
			else: 
				self.namespace['name_index'].pop(nickname)
		
		return (None, False)


	def setNickname(self, parent, nickname):
		"""
		Abbreviated name can't be numeric (an array index), and it can't be a string-replace % variable
		"""
		if not nickname.isdigit() and not '%(' in nickname:
			if DEBUG > 0: print ('Overwriting "%s"' if nickname in self.namespace['name_index'] else 'Setting "%s"') % nickname
			self.namespace['name_index'][nickname] = parent
	
	# Goes through given hierarchy, creating namespace references. 
	# Note, if a name shows up a few times, only latest will get nickname pointer.
	def setNicknames(self, term, termdict):
		self.namespace['name_index'][term] = termdict
		if isinstance(termdict[term], dict):
			for term2 in termdict[term]:
				self.setNicknames(term2, termdict[term])
		
		
	def getSelfDir(self): 
		return os.path.dirname(sys._getframe().f_code.co_filename)
		
		
	def get_command_line(self):
		"""
		*************************** Parse Command Line *****************************
		"""
		parser = MyParser(
			description = 'Report Calc for Quality Control (RCQC) is an interpreter for the RCQC scripting language for text-mining log and data files to create reports and to control workflow within a workflow engine. It works as a python command line tool and also as a Galaxy bioinformatics platform tool.  See https://github.com/Public-Health-Bioinformatics/rcqc',
			usage = 'rcqc.py [options]*',
			epilog="""  """)
		
		# Standard code version identifier.
		parser.add_option('-v', '--version', dest='code_version', default=False,
		action='store_true',	help='Return version of report_calc.py code.')

		parser.add_option('-H', '--HTML', type='string', dest='output_html_file',  
		help='Output HTML report to this file. (Mainly for Galaxy tool use to display output folder files.)')

		parser.add_option('-f', '--folder', type='string', dest='output_folder',  
		help='Output files (via writeFile() ) will be written to this folder.  Defaults to working folder.')

		parser.add_option('-i', '--input', type='string', dest='input_file_paths',  
		help='Provide input file information in format: [file1 path]:[file1 label][file1 suffix][space][file2 path]:[file2 label]:[file2 suffix] ... note that labels can\'t have spaces in them. ')

		parser.add_option('-d', '--daisychain', type='string', dest='daisychain_file_path',  
		help='Provide file path of previously generated report to load into report/ namespace.  Used to create a cumulative report.')
		
		parser.add_option('-o', '--output', type='string', dest='output_json_file',  
		help='Output report to this file, or to stdout if none given.')

		parser.add_option('-r', '--recipe', type='string', dest='recipe_file_path',  
		help='Read recipe script from this file.')

		parser.add_option('-j', '--json', type='string', dest='json_object',  
		help='A JSON object to place directly in top level namespace.')
		
		parser.add_option('-O', '--options', type='string', dest='optional_sections',  default='',
		help='Optional sections to execute.')  
		
		parser.add_option('-c', '--custom', type='string', dest='custom_rules', help='Provide custom rules in addition to (or to override) rules from a file.  Helpful for testing variations.')

		parser.add_option('-s', '--save_rules', type='string', dest='save_rules_path', help='Save modified ruleset to a file.')

		parser.add_option('-D', '--debug', action='store_true', dest='debug', help='Provides more detail about rule execution on stdout.')

		return parser.parse_args()

	
if __name__ == '__main__':

	rcqc = RCQCInterpreter()
	rcqc.__main__()

