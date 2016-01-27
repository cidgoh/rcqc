#!/usr/bin/python
# -*- coding: utf-8 -*-

import datetime
import glob
import json
import operator
import optparse
import math
import os
import pyparsing
import re
import sys

# These three classes, plus self.functions below, provide all of the functions available in rules to massage report data
from rcqc_functions.rcqc_functions import RCQCClassFnExtension
from rcqc_functions.rcqc_functions import RCQCStaticFnExtension

CODE_VERSION = '0.0.7'
DEBUG = 0
# 3 place infix operators e.g. "a < b" conversion to equivalent "lt(a b)" phrase.  Allowing all items with < and > in them to be referenced as gt lt etc. because otherwise Galaxy currently convers "<" to &gt; entity.
RCQC_OPERATOR_3 = {
	'<': 'lt',
	'lt': 'lt',
	'>':'gt',
	'gt':'gt',
	'>=':'ge',
	'ge':'ge',
	'==':'eq',
	'<=':'le',
	'le':'le',
	'!=':'ne',
	'<>':'ne',
	'ne':'ne',
	'*':'mul',
	'**':'pow',
	'/':'truediv',
	'//':'truediv',
	'-':'sub',
	'+':'add',
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

class ReportCalc(object):
	"""
	The ReportCalc class 
	
	General notes:
		Most iterables yield (over and over) a dictionary containing a "value" field (usually originating from a named group regular expression of form "...<?P<name>[match expression...]>...".  Usually this includes a "DICT_ROW" key which is the row offset (or count) of the current row result since start of iterable.
	"""
	def __init__(self):

		self.version = None
		self.options = None
		self.function_stack = [] # stack of functions called, from top-level to currently executing one
		
		# namespace includes variables and rules
		self.namespace = {} # Will be hash list of input files of whatever textual content
		self.namespace['report'] = {}
		self.namespace['report']['title'] = "Galaxy Report Calc"			
		self.namespace['report']['tool_version'] = CODE_VERSION	
		self.namespace['report']['job'] = {'status': 'ok'}
		self.namespace['report']['quality_control'] =  {'status': 'ok'}

		self.namespace['rulesets'] = []
		self.namespace['rule_index'] = {} # rule index based on location of store(_, location) field. 1 per.
		self.namespace['name_index'] = {} # index based on last (z) key of x.y.z namespace reference.
		self.namespace['files'] = [] 
		self.namespace['file_names'] = {} 
		self.namespace['iterator'] = {} # Provides the dictionary for each current function evaluation (at call depth). 
		self.namespace['report_html'] = ''	
				
		self.input_file_paths = None	
		self.ruleset_file_path = None	
		self.output_json_file = None	

		# Really core functions below require access to RCQC class variables.  
		# Other functions can be added in rcqc_functions RCQCClassFnExtension and RCQCStaticFnExtension classes.
		self.functions = {
			'store': self.storeNamespaceValue, 
			'store_array': self.storeNamespaceValueAsArray,
			'if': self.fnIf,
			'fail': self.fail,
			'exit': self.exit,
			'-': lambda x: operator.neg(x), # One of the few unary operators.
			'not': lambda x: operator.not_(x) 
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

		if options.output_html_file: 
			self.output_html_file = options.output_html_file 	#-H [file]
		self.output_folder = options.output_folder if options.output_folder else os.getcwd() #-f [folder]
		if options.input_file_paths: 
			self.input_file_paths = options.input_file_paths.strip()	#-i [string]

		self.execute = map(str.strip, options.execute.strip().strip(",").split(",") ) #cleanup list of execute sections

		# ************ MAIN CONTROL ***************
		self.getRules()

		print "Executing: " , self.execute, " from " , [str(item['name']) for item in self.namespace['rulesets'] ]

		if self.input_file_paths:
			self.getInputFiles()
		self.applyRules(self.execute)

		mytimedelta = datetime.datetime.utcnow() -_nowabout
		print "Completed in %d.%d seconds." % (mytimedelta.seconds, mytimedelta.microseconds)

		self.exit()


	def exit(self, exit_code = 0, message = ''):
		"""
		exit(exit_code = 0) -- Stops processing ruleset immediately and exits with given code.  It will finish composing and saving report files first.
		"""
		location = 'report/job'
		
		if self.options.output_json_file:
			self.writeJSONReport(self.options.output_json_file)		
		if self.options.output_html_file:
			self.writeHTMLReport('Report Summary')
			
		if exit_code == 1:
			self.storeNamespaceValue("FAIL", location + '/status')
		if exit_code == 2:
			self.storeNamespaceValue("RETRY", location + '/status')
			
		# Failure trigger if report/job/status == "FAIL"
		if 'job' in self.namespace['report'] and 'status' in self.namespace['report']['job']:
			status = self.namespace['report']['job']['status'].lower()
			if status == 'fail':
				exit_code = 1
				message = 'This job quality report triggered a workflow fail signal!'
			elif status == 'retry':
				exit_code = 2
				message = 'This job quality report triggered a workflow retry signal!'

		if message > '':
			self.storeNamespaceValue(message, location + '/message')	
					
		stop_err(message, exit_code)

	
	def fail(self, location = 'report/job', message = ''):
		"""
		fail(location=report/job, message='') -- sets value of location/status to "FAIL" (and continues rule processing) .  Short for store(FAIL, location).  Adds optional message.  If location is report/job, this will fail it.
		"""
		if location == 'report/job/status': location = 'report/job'
		self.storeNamespaceValue("FAIL", location + '/status')
		if message > '':		
			self.storeNamespaceValue(message, location + '/message')	


	def applyRules(self, execute_sections):
		"""
		Now apply each rule.  A rule consists of one or more functions followed by parameters.
		Currently a function having optional parameters is not allowed.
		"""
		if DEBUG > 0: print self.namespace['rulesets']
		
		for section in self.namespace['rulesets']:
			if section['name'] in execute_sections:
				for (row, myRule) in enumerate(section['rules']):
					self.rule_row = row
					self.function_stack = []
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
		
		termStr = myList[0] 
		if not termStr:
			print 'A funtion expression is empty in rule #' + str(self.rule_row)			
			return
		
		term = termStr	
		#term = None			
		#try: # Might be an indirect reference to a function.  Skip this?
		#	term = self.namespaceReadValue(termStr)
		#except TypeError as e: 
		#	self.ruleError(e)
		#	return None
		
		if isinstance(term, basestring): # Possibly this is a function
			childFn = self.matchFunction(term)
			if childFn:
				return self.executeFunction(childFn, myList)
		
		"""
		# Works, but best positioned in rule parser, 2nd pass after rules saved.
		if len(myList) > 2:
			myList = self.infixToPrefix(myList)
			if len(myList) == 1 and isinstance(myList[0], list):
				myList = myList[0]
			term = myList[0] 
			#print myList
			if isinstance(term, basestring): # Possibly this is a function
				childFn = self.matchFunction(term)
				#print "Found infix", term, myList
				if childFn:
					return self.executeFunction(childFn, myList)
		"""
		
		# Nothing to evaluate, so just return this verbatim.
		print "RETURNING (no function): ", myList
		return myList


	def executeFunction(self, childFn, myList):
	
		result = None
		self.function_stack.append(childFn) #Save so subordinate functions have access to their caller
		# Parameter is a function so evaluate it.  Could get a constant , dict or iterable back.
		try:
		#if True:
			fnObj = self.evaluateParams( childFn, myList[1:])

			# Finally execute function on arguments.	
			if DEBUG > 0: print 'Executing function:', fnObj['name'], fnObj['args']			
			if childFn['static'] == True: 
				result = fnObj['fn'](*fnObj['args'])
				
				if childFn['inplace'] == True:
					# If this is an in-place function, it means we need to swap out a temp variable for 1st arg and then set it via namespace.  
					# result = fnObj['fn'](inplace, fnObj['args'][1])
					self.storeNamespaceValue(result, fnObj['argText'][0], False)
				
			else: # These functions need access to Report Calc instance's namespace or functions:
				myobj = RCQCClassFnExtension(self)
				result = fnObj['fn'](* ([myobj] + fnObj['args']) )
				
			if DEBUG > 0: print "Result: ", result

		#An "iterator is not subscriptable" error will occur if program tries to reference namespace/iterator/x where x doesn't exist.
		# Error handling notes:https://doughellmann.com/blog/2009/06/19/python-exception-handling-techniques/

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
		
		#if True:					
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
	 	print 'Rule #%s: %s(%s) problem %s :\n %s ' % ( self.rule_row, fn_name, args, type(e), str(e))
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

		# TESTING: If INFIX (a < b) operators exist in parameter list, rewrite as prefix lt(a b) .
		# Should move this to rule parser 2nd pass. (After rules are saved to file option)
		# NOTE: ORDER OR PRECIDENCE IS SIMPLY LEFT TO RIGHT
		#parameterList = self.infixToPrefix(parameterList)		
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
						
					# If the result of evaluating the first argument = False	
					if param1 == False:
				
						# The "if" and "iif" functions don't have subsequent arguments evaluated
						if argCt == 1:
							skipEval = True # Appends further parameters to fn args but does not evaluate them.

						# "iif" also has 3rd argument which IS evaluated if first one is false. (Later args are also evaluated).
						elif argCt == 2  and ruleObj['name'] == 'iif':
						 	skipEval = False # Proceed to evaluate 3rd etc argument.

				elif functionName in ['getitem', 'iterate']: 
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
						
					else:
	  					
	  					# If parameter is quoted, pass it as is. In this way we pass 
	  					# string value which is never looked up against namespace.
	  					if isinstance(termStr, basestring) and termStr[0] == termStr[-1] == '"':
		  					result = termStr[1:-1]
	  						
	  					# Exception: when store(value location ...) called, must evaluate
	  					# value but not location (location evaluated by store function dynamically).
	  					elif not (functionName == 'store' and parameterCount==2) :
							# Try parameter match to a namespace variable's value
							result = self.namespaceReadValue(termStr)
	
	  					# Could we use a de() delayed execution function 
	  					# to preserve quotes for some functions to process?

				# After adding new argument to current rule, re-evaluate it with respect to queue ...	
				ruleObj['args'].append(result)
				ruleObj['argText'].append( str(termStr) )
			
			# When all parameters have been analyzed, return the function object.
			if len(parameterList) == 0:
				return ruleObj
		
	"""	
	def infixToPrefix(self, parameterList):
		while len(parameterList) > 2:
			testOperator = parameterList[1]
			if isinstance(testOperator, basestring ) and testOperator in RCQC_OPERATOR_3:
				# Revises function call so it is in prefix notation
				prefixFn = RCQC_OPERATOR_3[ testOperator ]
				parameterList = [ [ prefixFn , parameterList[0], parameterList[2] ] ] + parameterList[3:]

			else:
				break
				
		return parameterList
	"""	
		
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
		if not isinstance(location, basestring):
			raise TypeError ("Location needs to be a namespace path string of form x/y/z.  It may include x/y{namespace_reference}/z substitutions.")
	
		fnDepth = str(len(self.function_stack)-1)
		self.namespace['iterator'][fnDepth] = None

		valueObj = self.namespaceSearchReplace(valueObj)
		location = self.namespaceSearchReplace(location, True)
						
		#Note: for "a/b/c", this creates a dictionary obj called "b" at "a/b" if it doesn't exist already.
		print location
		
		(obj, key) = self.getNamespace(location) 

		# This catches case where valueObj is not an iterable.  It is a simple string, number, or boolean.
		if not (hasattr(valueObj, '__iter__') or isinstance( valueObj, (dict, list) ) ):
			if DEBUG > 0: print "store(..., %s) = %s" % (location, valueObj)		
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
				
		else: # Save all rows as array to single entry.  Note, final location doesn't see iterations?
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

			if DEBUG > 0: print "Set single entry (%s) /%s" % (location, key)


		# There is no way to see if an iterable has content without starting to execute it.  So we have to check  for emptiness via a flag.
		if not found: 
			obj[key] = None
			print "No results, can't set (%s) " % location
			return False		
		
		return True


	def namespaceSearchReplace(self, location, convert=False):
		"""
		convert=True: causes {name} expression to be converted to python %(name)s expression if {name} not found in namespace.  Means it was meant for narrower iterator dictionary search and replace scope.
		"""
		
		if not isinstance(location, basestring) or not '{' in location:
			return location

		# Check case where string substitutions "a/b{name}/c" point to namespace locations:
		# Note: this might conflict with dictionary terms.  It is up to programmer to avoid namespace vs dictionary term confusion (e.g. "value" or "name" used as variables and dictionary keys).  Or we add distinguishing mark for dictionary lookup.

		locationPath = re.split('({[^{}]+})', location)
		print "S&R:" , locationPath
		for ptr, phrase in enumerate(locationPath):
			if len(phrase) > 0 and phrase[0] == '{' and phrase[-1] == '}':
				reference = phrase[1:-1]
				newReference = self.namespaceReadValue(reference)
				if isinstance(newReference, basestring):
					if reference != newReference:	
						locationPath[ptr] = newReference 

					elif convert == True: 
						# If no change in value then it wasn't recognized in namespace.
						# So convert it to dictionary lookup %([phrase])s instead.
						locationPath[ptr] = '%(' + reference + ')s'
				
				#else: #Lookup should have matched a namespace string value.
		locationPath = ''.join(locationPath)
		print "S&R:" , locationPath
		return ''.join(locationPath)


	def getRules(self):
				
		if self.options.rules_file_path and self.options.rules_file_path != 'None':
			self.rules_file_path = self.options.rules_file_path
			if not os.path.exists(self.rules_file_path):
			 	stop_err('Unable to locate the rule file!\nWorking folder: %s \nRules file: %s' %(os.getcwd(), self.rules_file_path) )
			 	
			with open(self.rules_file_path,'r') as rules_handle:
				rulefileobj =  json.load(rules_handle)
		else:
			# Provides a default empty ruleset to add customized rules to.
			rulefileobj = {
				'rulesets':[{
					'name':'processing',
					'rules':[]
				}]
			}
			self.execute = ['processing']
			
		self.namespace['rulesets'] = rulefileobj['rulesets']

		if self.options.custom_rules:
			# options.custom_rules is a short-lived file, existing only so long as tool is executing.
			# The Galaxy tool <configfile> tag writes this content directly as json data.
			#with open(self.options.custom_rules,'r') as rules_handle: print  rules_handle.read()
			
			with open(self.options.custom_rules,'r') as rules_handle:
				# Will throw ValueError if % isn't escaped
				self.custom_rules = json.load(rules_handle)
			
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
				
				for ruleset in self.namespace['rulesets']:
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
					print "Parsed new rule: " , parsed_rule	
					if row == "None": #If no row given, append rule.
						rule_section.append(parsed_rule)
					else: # Insert rule in right spot in report's rulebase. 
						rule_section.insert(int(row)+ptr2+1, parsed_rule)

				# Now drop any rules (working from highest row rule mod to lowest).
				if rule_group['drop'] > 0:
					if row == "None":
						stop_err('In order to delete a number of rules, one must select starting rule row using "At rule" input.')			
					print "dropping ", row, rule_group['drop']		
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
			# Only the rulesets part of a rulefile object can change; the other attributes are copied from ruleset file.
			rulefileobj['rulesets'] = self.namespace['rulesets'] 
			with (open(self.options.save_rules_path,'w')) as output_handle:
				output_handle.write(json.dumps(rulefileobj,  sort_keys=True, indent=4, separators=(',', ': ')))

		# TESTING: INFIX OPERATORS
		# Now, since they're saved, go back over rules and convert any infix expressions to prefix
		for rule_section in self.namespace['rulesets']:
			for (ptr, rule) in enumerate(rule_section['rules']):
				rule_section['rules'][ptr] = self.infixToPrefixRewrite(rule)
				#print rule_section['rules'][ptr] 

	def infixToPrefixRewrite(self, rule): # given rule is always an array
		"""
		Revises any rule so that any [a fn b] is rewritten [fn a b] , recursively.
		2 cases: bracketed expression: [abs 1 + 2 + 3]
		or function with brackets[abs [ 1 + 2 + 3]]
		"""
		change = True
		while change:
			change = False
			if len(rule) > 2 and isinstance(rule[1], basestring ) and rule[1] in RCQC_OPERATOR_3:
				# Revises function call so it is in prefix notation				
				rule = [ [ RCQC_OPERATOR_3[ rule[1] ] ,rule[0], rule[2] ] ] + rule[3:]
				change = True
				
			if len(rule) > 3 and isinstance(rule[2], basestring ) and rule[2] in RCQC_OPERATOR_3:
				rule = [rule[0], [ RCQC_OPERATOR_3[ rule[2] ] ,rule[1], rule[3] ] ] + rule[4:]
				change = True
			
		for ptr, term in enumerate(rule):
			if isinstance(term, list ): 
				rule[ptr] = self.infixToPrefixRewrite(term)	
				while len(rule[ptr]) == 1:
					if isinstance(rule[ptr][0], list ):  # Simplify ((((fn a b))))
						rule[ptr] = rule[ptr][0]
					else:
						break

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
		#item = item.encode('utf8') # parse returns only unicode; better for matching quotes?
		#item = str(item) # BASIC ASCII FOR NOW
		
		# All items having quotes are taken as literal strings
		if item[0] == '"' and item[-1] == '"': # Drop quotes around term; it remains a string.
			# item = item[1:-1]
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
				'file_name': file_name,
				'file_path': file_path,
				'file_type': file_type
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
		"""
		report = json.dumps(self.namespace['report'], sort_keys=True, indent=4, separators=(',', ': '), default=lambda: "[nasty iterable]")
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
			raise TypeError ("Problem: getNamespace() given a non-string argument for location")
		
		focus = self.namespace
		splitName = myName.split('/')
		# Retrieval of shortcut variable name .z when original name is x.y.z		
		if myName[0] == '/':
			if len(myName) == 1:
				# Not a good path: '/'
				raise ValueError ("Problem: given location is just an empty path '/'")
		
			if len(splitName)  == 2: 
				lastTerm = splitName[-1]
				if lastTerm in self.namespace['name_index']:
					#print "Found (_, %s)" % lastTerm
					return (self.namespace['name_index'][lastTerm], lastTerm)
			return myName

		for (ptr, part) in enumerate(splitName):
			if ptr == len(splitName)-1:
				if not isinstance(focus, dict):
					raise TypeError('The namespace path "%s" isn\'t a dictionary but it needs to be.  Did a rule previously set it to a constant?' % '/'.join(splitName[0:ptr]) )
					
				# Abbreviated name can't be numeric (an array index), and it can't be a string-replace % variable
				if isinstance (part, basestring) and not part.isdigit() and not '%(' in part:
					if DEBUG > 0: print ('Overwriting "/%s"' if part in self.namespace['name_index'] else 'Setting "/%s"') % part
					self.namespace['name_index'][part] = focus

				return (focus, part)
			if part in focus: 	
				focus = focus[part] # Advance along path
			else:
				focus[part] = {}
				focus = focus[part]


	def namespaceReadValue(self, myName):
		"""
		Attempts to find value in appropriate path, and return that object or value; 
		But if not found, will return myName as a literal.
		Assumes all a/b{name}/c substitutions have already been done.
		"""
		if not isinstance(myName, basestring):
			return myName
		
		if len(myName) == 0:
			return ""
			
		focus = self.namespace		
		
		# TESTING: NO LEADING SLASH FOR ABBREVIATION:
		# Means "report" can get confused with bottom level variable if someone set that.
		# So global namespace context may be too much.
		# Maybe search top-level first
		if not '/' in myName:
			if myName in focus: # Check for root variable reference first
				return focus[myName]
			
			# Check for (latest) leaf variable reference
			(reference, returnable) = self.getNickname(myName)
			if returnable:
				return reference
		
		
		splitName = myName.split('/')

		# Determine if we are looking at an abbreviation "/[leaf variable name]"
		# PHASE THIS OUT ???
		if myName[0] == '/':
			if len(splitName) == 2: 
				(reference, returnable) = self.getNickname(splitName[1])
				if returnable:
					return reference
			return myName # No nickname so returning literal "/whatever".
			
			
		
		for (ptr, part) in enumerate(splitName):
			if not focus == None and part in focus: 
				if not isinstance(focus, dict):
					raise TypeError('The location namespace path "%s" isn\'t a dictionary but it needs to be.  Did a rule previously set it to a constant?' % '/'.join(splitName[0:ptr]) )
							
				focus = focus[part] # Advance along path
			else:		
				return myName # Retain basestring data type.  Term is a literal expression

		return focus # now a value / object
	
	
	def getNickname(self, nickname):
		""" 
		Whenever the "store(... location)" function is called, a reverse lookup is set up on the leaf c part of the location's a/b/c path to point to the full path.  Thus c can be a nickname to the latest use of the term.  The only issue arises if c is overwritten by other processes that happen to store paths with the same c leaf. In such cases programmers must change rule references to a leaf name, or stick to the full path a/b/c reference for that variable.
		"""
		if nickname in self.namespace['name_index']: #find shortcut "/myname" type variable references
			parentDict = self.namespace['name_index'][nickname]
			if DEBUG: print 'Found "/%s"' % nickname
			if nickname in parentDict:
				return (parentDict[nickname], True)
			else: # indicates something changed nickname's entry/ data structure path
				self.namespace['name_index'].pop(nickname)
		
		return (None, False)
		
		
	def get_command_line(self):
		"""
		*************************** Parse Command Line *****************************
		"""
		parser = MyParser(
			description = 'Records selected input text file fields into a report (json format), and optionally applies tests to them to generate a pass/warn/fail status. Program can be set to throw an exception based on fail states.',
			usage = 'report_calc.py [ruleSet file] [input files] [options]*',
			epilog="""
        USAGE
        
        """)
		
		# Standard code version identifier.
		parser.add_option('-v', '--version', dest='code_version', default=False,
		action='store_true',	help='Return version of report_calc.py code.')

		parser.add_option('-H', '--HTML', type='string', dest='output_html_file',  
		help='Output HTML report to this file. (Mainly for Galaxy tool use to display output folder files.)')

		parser.add_option('-f', '--folder', type='string', dest='output_folder',  
		help='Output files (via writeFile() ) will be written to this folder.  Defaults to working folder.')

		parser.add_option('-i', '--input', type='string', dest='input_file_paths',  
		help='Provide input file information in format: [file1 path]:[file1 label][file1 suffix][space][file2 path]:[file2 label]:[file2 suffix] ... note that labels can\'t have spaces in them. ')
		
		parser.add_option('-o', '--output', type='string', dest='output_json_file',  
		help='Output report to this file, or to stdout if none given.')

		parser.add_option('-r', '--rules', type='string', dest='rules_file_path',  
		help='Read rules from this file.')

		parser.add_option('-e', '--execute', type='string', dest='execute',  default='',
		help='Ruleset sections to execute.')  
		
		parser.add_option('-c', '--custom', type='string', dest='custom_rules', help='Provide custom rules in addition to (or to override) rules from a file.  Helpful for testing variations.')

		parser.add_option('-s', '--save_rules', type='string', dest='save_rules_path', help='Save modified ruleset to a file.')

		parser.add_option('-d', '--debug', action='store_true', dest='debug', help='Provides more detail about rule execution on stdout.')

		return parser.parse_args()

	
if __name__ == '__main__':

	rc = ReportCalc()
	rc.__main__()

