#!/usr/bin/python
# -*- coding: utf-8 -*-
import sys
import fnmatch
import re
import os.path
import datetime
import collections
import dateutil.parser as dateparser
import math
import operator

try: #Python 2.7
	from collections import OrderedDict
except ImportError: # Python 2.6
	from ordereddict import OrderedDict
	
try:	
	import simplejson as json
except ImportError: # Python 2.6
    	import json
    	
DEBUG = 0

def stop_err( msg, exit_code=1 ):
	sys.stderr.write("%s\n" % msg)
	sys.exit(exit_code)
	
"""
	The functions below primarily exist for use in user's rulesets, but a few are also used directly in report_calc.py engine.
	http://stackoverflow.com/questions/4473184/unbound-method-f-must-be-called-with-fibo-instance-as-first-argument-got-cla
"""
################################### STATIC FUNCTIONS ################################

class RCQCStaticFnExtension(object):
	"""
	These functions ldon't need access to the RC engine's methods or current namespace.
	PRECEED THESE METHODS WITH @staticmethod, or else you will receive 
	"TypeError:unbound method X must be called with RCQCStaticFnExtension instance as first argument..."
	"""	

		
	@staticmethod
	def basename(string):
		"""
		basename(string) -- Return file name and suffix of file path
		"""	
		return os.path.basename(string)
		
		
	@staticmethod
	def between(compare, lower_bound, upper_bound):
		"""
		between(compare, lower_bound, upper_bound) -- True if lower_bound <= compare <= upper_bound.
		This range test works for both string and numeric data. 
		"""	
		return ( compare >= lower_bound and compare < upper_bound )

 
 	@staticmethod
	def join(delimiter, *items):
		"""
		join(string1, string2 etc) -- return all strings concatenated. 
		Extend this to integers etc?
		"""
		return delimiter.join(items)	
		
		
	@staticmethod	
	def getHtml(content, title='', depth=0): 
		"""
		getHtml(location, title, depth=0) -- Returns object at location as HTML string.  Indented starting with tabs of given depth
		In this case "content" is not iterable (not a function having yeild).
		"""
		formating = {
			'tabs': '	' * depth, #Json encoded
			'title': title,
			'depth': depth,
			'trHead': '',
			'trPrefix': '',
			'trSuffix': ''
			}

		if isinstance(content, (dict,list)):
			# Sorting keys so that tables (iterable within an iterable)
			if  isinstance(content, dict): 
				#Sorts dictionary keys alphabetically but with non-atomic (object) items last in list.
				content_iterable = 	iter(sorted(content.items(), key=lambda (mykey, myvalue): hasattr(myvalue, '__iter__') )) 
				formating['content'] = '\n'.join([RCQCStaticFnExtension.getHtml(value, key, depth+1) for (key, value) in content_iterable])
					
			else: # list here.
				# If every item has the same dictionary keys then show it as a table.
				if RCQCStaticFnExtension.__isTable__(content):
					keys = content[0].keys()
					formating['trHead'] = '<tr><td>' +'</td><td>'.join( keys ) + '</td></tr>\n'
					formating['content'] = ''
					for (ptr, myDict) in enumerate(content):
						cells = ''
						for key in keys:
							value = myDict[key]
							numeric = '' if isinstance(value, basestring) else  ' class="numeric"' 
							cells += '<td%s>%s</td>' % (numeric, value)
						formating['content'] += '<tr>' + cells + '</tr>\n'

				else: # Show as a mish-mash
					content_iterable = enumerate(content)
					formating['content'] = '\n'.join([RCQCStaticFnExtension.getHtml(value, key, depth+1) for (key, value) in content_iterable])
			
			if depth > 0: # Inside a table here
				formating['trPrefix'] = '<tr><td colspan="2">'
				formating['trSuffix'] = '</td></tr>'
				
			return """
%(tabs)s%(trPrefix)s<table class="RCQC depth_%(depth)s">
%(tabs)s	<caption>%(title)s</caption>
%(tabs)s	<thead>%(trHead)s</thead>
%(tabs)s	<tbody>%(content)s</tbody>
%(tabs)s	<tfoot></tfoot>
%(tabs)s</table>%(trSuffix)s\n"""  % formating
		
		else:
			formating['content'] = content
			formating['numeric'] = '' if isinstance(content, basestring) else  ' class="numeric"' 
			return '<tr><td>%(title)s</td%(numeric)s><td>%(content)s</td></tr>' % formating
		
		
	@staticmethod
	def __isTable__(content):
		"""
		isTable(content) -- Checks to see if each item in content array is a dictionary with the same keys 
		"""
		if len(content) == 0: 
			return False
		for (ptr,item) in enumerate(content):
			if not isinstance(item, dict):	return False
			if ptr == 0:
				dictKeySet = set(item.keys() )
			else:
				# If one or other has a different key, we don't have a table
				if len(dictKeySet ^ set(item.keys()) ) > 0: return False
		return True
					
					
	@staticmethod	
	def first(location): 
		"""
		first(location) -- Returns first element of existing list at location, or None.
		"""
		return  getitem(location, 0) if isinstance(location, list) else None		
		
				
	@staticmethod	
	def iif(x,y,z): 
		"""
		iif (conditional, true_expression, false_expression) -- If conditional is true, evaluate true_exp, else evaluate false_exp
		Note the expressions have already been evaluated appropriately by interpreter.  What this does is RETURN the 2nd or 3rd expression.
		"""
		return y if x else z


	@staticmethod	
	def all(*arg): 
		"""
		all (statement ...) -- executes each given function unconditionally. Implicit in ( fn1(), fn2(), ...) expression.
		"""
		return arg
		
		
	@staticmethod
	def iterValue(iterator):
		"""
		iterValue(iterator) -- Returns only iterator's FIRST result dictionary's 'value' field - uses "RETURN()"
		"""
		for mydict in iterator:
			return mydict['value']


	@staticmethod
	def iterValueArray(iterator):
		"""
		iterValueArray(iterator) -- Returns iterator result dictionary 'value' fields as an array
		"""
		result = []
		for mydict in iterator:
			result.append( mydict['value'] )
		return result


	@staticmethod
	def length(expression):
		"""
		length(expression) -- calculate length of string or list.
		TEST __iter__ function.  Means returned value for each iteration is length of that iteration's content.
		"""
		if  hasattr(expression, '__iter__') and not isinstance(expression, list):
			return RCQCStaticFnExtension.iterLength(expression)
		else:
			return len(expression) # could be a location of an array, or a string. 

				
	@staticmethod	
	def last(location): 
		"""
		last(location) -- Returns last element of existing list at location, or None.
		"""
		#print "LAST ", location, type(location),getitem(location, -1)
		return  location[-1] if isinstance(location, list) else None


	@staticmethod
	def nameCamelCase(myString, default='no_label'):
		"""
		nameCamelCase(string) -- Returns camel case version of given string.
		"""
		myString = myString.replace('#','_count_').replace("+",'_plus_').replace('%','_percent_')
		output = ''.join(x for x in myString.title().strip() if x.isalnum())
		try:
			return output[0].lower() + output[1:]
		except IndexError as e:
			print 'Unable to convert "%s" to camelCase.' % myString
			if len(myString) > 0:
				return myString
			else:
				return default
		 
		
	@staticmethod
	def nameUnderScore(myString, default='no_label'):
		"""
		nameUnderScore(string) -- Returns lowercase version of given string, with spaces replaced by underscore.
		"""	
		myString = myString.lower().replace('#','_count_').replace("+",'_plus_').replace('%','_percent_')
		output = ''.join(x for x in myString if x.isalnum() or x in ' _').replace(' ','_')
		if len(output): return output
		else: return default
  
		
	@staticmethod
	def note(*arg):
		"""
		note(text, text, ...) -- To make comments.  A statement can be commented out this way too.
		"""
		return True

	
	@staticmethod      
	def parseDataType(myValue):
		"""
		parseDataType(string) -- Try to recognize booleans, integer and float from given text string.
		Issue: text search (like regex) returns numbers and booleans as text.  

		IMPLEMENT???  Conversion to numbers can be overridden by providing a 'format' string).
		"""
		# All non-string types accepted as is, e.g. int, float, long, list, dict
		if not isinstance(myValue, basestring):  
			return myValue

		if myValue.lower() == 'true': return True
		if myValue.lower() == 'false': return False
	
		try:
			return int(myValue.replace(',','') )
		except ValueError:
			try:
				return float(myValue.replace(',','') )
			except ValueError:
				return myValue #remains string
			
		
	@staticmethod
	def parseFixedWidth(myText):
		"""
		parseFixedWidth(text) -- Convert a text file with fixed-width columnar data into tabular text, so it can be processed by getTabular()
		- Assumes any lines that have no spaces in them can be skipped.
		- Also assumes that header labels are sparated by at least two spaces.
		# FUTURE: Allow for skipping lines by comment character
		# Issue, can't iterate this in one pass because need to identify columns first.
		"""
		spaces = []
		output = []
		header = None
		linecount = 0
		maxlen = 0
		for line in myText.split('\n'):
			if line.strip().find(' ') >= 0: #If line has at least one meaningful space delimiter
				linecount += 1
				if len(line) > maxlen: 
					maxlen = len(line)

				if linecount < 3:	
					if linecount ==1:
						header = line
					if linecount == 2: # past header, and into real data. #get real data/header line length here:
						spaces = [column for column, char in enumerate(line) if char == ' ']
					continue
				
				for column in reversed(spaces):
					if line[column] != ' ': spaces.remove(column) 

		# Consolidate consecutive space columns into first one.
		for column in reversed(spaces):
			if column - 1 in spaces:
				spaces.remove(column)
		
		for ptr, column in enumerate(spaces):
			column1 = header.find('  ',column)
			if column1 > -1:
				spaces[ptr] = column1
		
		# Ensure 1st column is 0 (data could start immediately)
		if spaces[0] != 0: spaces.insert(0,0)
		# Ensure last column is end of line column
		if not maxlen-1 in spaces: spaces += [maxlen-1]
		
		# Spaces[] now has column boundaries.
		for line in myText.split('\n'):
			if line.strip().find(' ') >= 0: # skip cosmetic lines again.
				lineout = []
				for ptr,column in enumerate(spaces[1 : ]):
					lineout.append(line[spaces[ptr] : column].strip() )
	
				output += ['\t'.join(lineout)]
		
		return output
				
		
	@staticmethod
	def parseDate(adate):
		"""
		parseDate(date_time_string) -- Convert human-entered time into linux integer timestamp
		This handles UTC & daylight savings exactly

		@param adate string Human entered date to parse into linux time
		@return integer Linux time equivalent or 0 if no date supplied
		"""
		adate = adate.strip()
		if adate == '':return 0

		return dateparser.parse(adate, fuzzy=True) #adateP =
		# return calendar.timegm(adateP.timetuple()) # linux time
	
		
	@staticmethod
	def statisticN(numlist, split=50, genome_length=0):
		"""
		statisticN(numeric_array, split=50, genome_length=None) -- By default, the N50 statistic of the passed array of contig lengths.

		The Broad Institute definition (https://www.broad.harvard.edu/crd/wiki/index.php/N50) is based on a real number statistic that allows for a "split" case, but this is not pertinent to genomic assembly contigs, so we have used a simpler version, namely "N50 is the length of the smallest contig in the set that contains the fewest (largest) contigs whose combined length represents at least 50% of the assembly. The N50 statistics for different assemblies are not comparable unless each is calculated using the same combined length value." This is described in these sources: 
		
		http://jermdemo.blogspot.ca/2008/11/calculating-n50-from-velvet-output.html
		https://en.wikipedia.org/wiki/N50,_L50,_and_related_statistics
		http://seqanswers.com/forums/showthread.php?p=41420
		
		INPUTS
		genome_length: Optional: reference genome length can be provided.
		"""
		if DEBUG: print numlist
	 	
		try:
			sorted_contigs = sorted(numlist, reverse=True)
		except: 
			raise AttributeError ("statisticN() didn't get a list of numbers to work on! ")
	 		return None
	 	
	 	assembly_length = math.fsum(sorted_contigs)
	 	n_length = assembly_length*split/100
	 	
	 	cumulative = 0
	 	for ptr, contig_length in enumerate(sorted_contigs):
	 		cumulative += contig_length
	 		if cumulative >= n_length:
	 			break

 		data = OrderedDict()
 		data[ 'contig_N' + str(split)] = contig_length
 
		if genome_length > 0:
	 		
	 		n_length = genome_length*split/100
		 	cumulative = 0
		 	for ptr, contig_length in enumerate(sorted_contigs):
		 		cumulative += contig_length
		 		if cumulative >= n_length:
		 			break
	 		
	 		data['contig_NG' + str(split) ] = contig_length

		data[ 'contig_L' + str(split)] = ptr
	 				
		if genome_length > 0:
	 		data['contig_LG' + str(split) ] = ptr	
	 					 	
	 	return data

	
	@staticmethod
	def parseInt(value):
		"""
		parseInt(number) -- Convert number (rounded) into an integer
		"""
		return int(round(value))
	
	
	@staticmethod
	def round(value, precision = 0):
		"""
		round(number, precision = 0) -- Round number to given precision
		"""
		return round(value, precision)
	
	@staticmethod
	def pageHtml(html_content, title="Data"):
		"""
		pageHtml(html_content, title) -- Wraps html_content with barebones html5 doctype etc. tags. 
		"""
		return """<!doctype html>
<html lang="en">
	<head>
		<meta charset="utf-8">
		<title>%s</title>
		<style>
			body {font:1rem arial}
			table.RCQC {border:1px solid silver; min-width:300px; border-collapse: collapse;
				display:inline-block;}
			table.RCQC td {padding:3px 3px 3px 5px}
			table.RCQC table td {padding-left:25px}
			table.RCQC td.numeric {text-align:right}
			table.RCQC caption {background-color: #BBB; display:block;
				text-align:left; padding:3px 3px 3px 5px; cursor:pointer;}

			table.RCQC tr td {border-bottom:1px solid silver}
			table.depth_0 caption {background-color: #EEE; font-size:1.3rem}
			table.depth_1 caption {background-color: #DDD; font-size:1.2rem}
			table.depth_2 caption {background-color: #CCC; font-size:1.1rem}

			@media screen {
				table.RCQC.depth_1 table {max-height:1.7rem;	display:block;overflow-y:scroll;}
				table.RCQC.depth_1 *:hover > table  {
				    -webkit-animation-name: example; /* Chrome, Safari, Opera */
				    -webkit-animation-duration: 3s; /* Chrome, Safari, Opera */
				    -webkit-animation-fill-mode: forwards; /* Chrome, Safari, Opera */
	    			animation-fill-mode: forwards;
				    animation-name: example;
				    animation-duration: .5s;
				    animation-delay: .3s;
				}

				/* Chrome, Safari, Opera */
				@-webkit-keyframes example { from {max-height:1.7rem} to {max-height:600px} }
				@keyframes example { from {max-height:1.7rem} to {max-height:600px} }
			}
		</style>
	</head>
	<body>
	%s
	</body>
</html>""" % (title, html_content)

################################### ITERABLES ###################################
		

	@staticmethod
	def iterLength(expression):
		"""
		iterLength(expression) -- enhances given list of dictionaries with a 'length' key = length of key 'value' content.
		"""
		for myDict in expression:
			myDict['length'] = len(myDict['value'])
			yield myDict


	@staticmethod
	def regexp(subjects, regex, clean_name=False):
		"""
		regexp(text regular_expression, clean_name=False) -- Apply python regular expression to text.  Use named groups (?P<value>...) to return result dictionary.  For optional (?P<name>...), clean_name=True on "A BC" yeilds "a_bc"; clean_name=camelCase yeilds "aBc".
		
		ROW is integer index of current match row 
		"""
		if not hasattr(subjects, '__iter__'):
			subjects = [subjects]
		
		for subject in subjects:
			if isinstance(subject, dict) and 'value' in subject:
				subject = subject['value']
			if not isinstance(subject, basestring):
			 	raise ValueError ( "regexp() didn't receive a string to search.")
			try:
				regexResult = re.finditer(regex, subject)
			except TypeError:
			 	raise TypeError ("regexp() couldn't compile the regular expression.")
		 	
		 	if DEBUG > 0: print 'Applying re "%s" to "%s ..."' % (regex, subject[0:50].replace('\n' , '\\n'))
		 	
		 	# To modify contents of an iterator as it is delivered, must deliver modification using "yeild"
			for ptr, myNextItem in enumerate(regexResult):
				
				myDict = myNextItem.groupdict()
				myDict['ROW'] = ptr
				if clean_name != False and 'name' in myDict:
					myDict['name'] =  RCQCStaticFnExtension.nameCamelCase(myDict['name']) if clean_name == 'camelCase' else RCQCStaticFnExtension.nameUnderScore(myDict['name'])
				if 'value' in myDict:
					myDict['value'] = RCQCStaticFnExtension.parseDataType(myDict['value'])
				else:
					myDict['value'] = ''
					
				yield myDict
	
	
	@staticmethod	
	def getRegExp(string): 
		"""
		getRegExp(string) -- Returns compiled regular expression.
		"""
		return re.compile(string)
	
	
	@staticmethod	
	def getTabular(content, column='data'): 
		"""
		getTabular(content, column='data') -- Converts content to tabular text data with headers.  If content is a dictionary, key / value rows are written; If content is an array of dictionary, inserts header having dictionary keys.  Otherwise one can supply getTabular with column header text.
		NOTE: no finer control exists over column header or row sorting
		"""
		
		if hasattr(content, '__iter__'):
			gotHeader = False
			if isinstance(content, dict):
				yield {'value': '\n'.join([key + '\t' + str(val) for (key, val) in content.iteritems()] ) }

			else: #each item is an atomic value (or perhaps a list?)
				for item in content:
					# An iterable of dictionaries is presented as tabular data with dictionary keys in first row.
					if isinstance(item, dict):
					
						if not gotHeader:
							gotHeader = True
							yield {'value':  '\t'.join(item.keys)+'\n'}
						yield  {'value':  '\t'.join([str(value) for (key,value) in item.iteritems()])+'\n' }

					else:
						if not gotHeader:
							gotHeader = True
							yield  {'value': column+'\n' } #name of array gets put into column header. 
						yield  {'value': str(item)+'\n' }

	
	@staticmethod	
	def importTabular(content, clean_name=False, skip_rows=0, tableHeader=None): 
		"""
		importTabular(content, clean_name=False|camelCase|underScore(default)) -- Converts content - carriage delimited text tabular row data - into a list of dictionary.
		ALLOW USER TO PROVIDE OWN COLUMN NAMES as comma-delimited string?
		Strange Error: Used "header=[]" but this seemed to create a global "header" variable that was set on first use.
		"""
		if DEBUG > 0: print "TableHeader", tableHeader
		
		if tableHeader == None:
			gotHeader = False
			tableHeader = [] 
		else: 
		 	gotHeader = True
		print "importTabular", gotHeader, skip_rows, tableHeader
		
		if isinstance(content, basestring):
			content = content.split('\n')
	
		if DEBUG > 0: print "Tabular content", content
		
		if not hasattr(content, '__iter__'):
			raise ValueError ("importTabular() didn't receive iterable text for input.")
			
		for row, line in enumerate(content):

			if row >= skip_rows:
				# Assuming each item of content is a line of text
				if isinstance(line, basestring) and len(line) > 0:
					if not gotHeader:
						gotHeader = True
						ptr = 0
						for item in line.strip().split('\t'):
							default = "col"+str(ptr)
							ptr += 1
							if clean_name == False:
								tableHeader.append(item)
							elif clean_name == 'camelCase':
								tableHeader.append( RCQCStaticFnExtension.nameCamelCase(item, default) )
							else:
								tableHeader.append( RCQCStaticFnExtension.nameUnderScore(item, default) )
					
							if DEBUG > 0: 	print "Found column: ", tableHeader[-1]
					
					else:
						myDict = OrderedDict()
						myDict['ROW'] = row - 1 - skip_rows # Subtract 1 if there is a header line.
						columnData = line.split('\t')
						for (column, item) in enumerate(tableHeader):
							myDict[item] = RCQCStaticFnExtension.parseDataType( columnData[column] )
						yield myDict


	@staticmethod	
	def exportTabular(content, label="", depth = 0): 
		"""
		exportTabular(content) -- export namespace (hierarchy) into tabular string format (rows end in carriage returns).
		"""
		output = ''
		
		if isinstance(content, dict):
			if len(label) >0 :
				output = depth*'	'+str( label if depth !=1 else label.upper())+'\n'
			# As with HTML display, put more complex items at bottom.
			content_iterable = 	iter(sorted(content.items(), key=lambda (mykey, myvalue): hasattr(myvalue, '__iter__') )) 
			for (key, value) in content_iterable:
				output += RCQCStaticFnExtension.exportTabular(value, key, depth+1)
		elif isinstance(content, list):
			if len(label) >0 :
				output = depth*'	'+str(label if depth !=1 else label.upper())+'\n'
			for ptr, item in enumerate(content):
				output += RCQCStaticFnExtension.exportTabular(item, ptr, depth+1)
		else:
			output = depth*'	'+str(label)+'	'+ str(content) + '\n'
			
		return output
			
	@staticmethod
	def format(myFormatString, dictOrValues):
		"""
		format(string, dictionary) -- Returns dictionary with all 'value' entries updated as per format string.
		"""
		if hasattr(dictOrValues, '__iter__'):
			for myDict in dictOrValues:
				myDict['value'] = myFormatString % myDict
				yield myDict
		else:
			yield myFormatString % dictOrValues
		
		
	@staticmethod
	def section(subject, start_phrase, end_phrase):
		"""
		section(text, start_phrase, end_phrase, regex) -- Match start/end phrase to section in text.  
		Allows simpler section identification start/end strings than single regex would otherwise need.
		"""

		startPtr = subject.find(start_phrase)
		while startPtr != -1:
			startPtr += len(start_phrase)
			endPtr = subject.find(end_phrase, startPtr)
			if endPtr != -1:
				yield {'value': subject[ startPtr : endPtr -1] } 
				startPtr = subject.find(start_phrase, startPtr)
			else:
				startPtr == -1


######################### FUNCTION EXTENSIONS THAT NEED RCQC SELF #######################
class RCQCClassFnExtension(object):
	"""
	These functions DO need access to the RC engine's methods or current namespace via self.callerInstance instance.
	"""
	def __init__(self, callerInstance):
		self.callerInstance = callerInstance
		
	def append(self, expression, location):
		"""
		append(value, location) -- Appends (possibly iterable) value to array at location.  Returns value
		Extra feature -	location doesn't have to be previously set to an array.	 Append	will do this.
		
		ISSUE: for clarity may want a separate appendValue() function.
		Since function parameters like location arrive evaluated, location is either a namespace node, 
		or it is a x/y/z path where x/y could already exist in namespace, and z is a new key.  Or x/y is new too.
		"""
		
		if isinstance(location, basestring):

			#location = self.callerInstance.namespaceSearchReplace(location)
			(obj, key) = self.callerInstance.getNamespace(location)
			if not key in obj: #Note, if key happens to be in obj but isn't a list that will cause problems.
				obj[key] = []
				print "append() setting up array for /" + key
				self.callerInstance.namespace['name_index'][key] = obj  
			location = obj[key] # Should be dictionary or array here.

		if  hasattr(expression, '__iter__'):
			value = None # might be empty iterator
			for item in expression: 
				if DEBUG > 0: print "append item", item
				# append one dictionary onto another = copy
				if isinstance(location, dict): # CHECK IF Expression is dict too?
					location[item] = expression[item]
					continue	
				elif isinstance(item, dict) and 'value' in item:
					location.append(item['value'])
					continue
				value = item
				location.append(value)
				
			return value

		location.append(expression)
		return expression

		
	def sorted(self, location):
		"""
			sorted(list) -- Applies standard sort to list.
			Future: enhance with other python sorted() attributes?
		"""      
		if isinstance(location, basestring):
			(obj, key) = self.callerInstance.getNamespace(location)
			location = obj[key]
			
		for item in sorted(location):
			yield {'value': item}		# Add ROW too?
		#return sorted(alist)
		
			
	def iterate(self, iterator, location, *functions):
		"""
		iterate (iterator location fn1 ... fn2 etc.) -- Iterate through iterator's dictionary, storing it in location, and then executing each function expression. 
		Iterator dictionary is also available in iterator/[fn depth]/
		"""
		# Catch non-iterables
		if not (hasattr(iterator, '__iter__') or isinstance(iterator, (dict, list)) ):
			raise ValueError ("iterate() didn't receive an iterator for input.")
			return None

		fnDepth = str(len(self.callerInstance.function_stack)-1)
		self.callerInstance.namespace['iterator'][fnDepth] = None
		
		found = 0
		for myDict in iterator:
			found = found + 1
			self.callerInstance.namespace['iterator'][fnDepth] = myDict
			if isinstance(location, basestring): # It should always be this.
				(obj, key) = self.callerInstance.getNamespace(location)
				obj[key] = myDict
				self.callerInstance.namespace['name_index'][key] = obj  #abbreviated name
			
			if DEBUG > 0: print 'Iterator/%s:' % fnDepth, self.callerInstance.namespace['iterator'][fnDepth], functions
			self.callerInstance.evaluateAuxFunctions(functions)

		if  found ==0: 
			print "Note, no iterations to do. "
			return False		
		if found > 1: print "Iterate() done ", found, " times."
		return True
		
		
	def iterMap(self, iterator, functionName):
		"""
		iterMap(iterator, function) -- Given function should be applied to each iterator dictionary's 'value' key, and result returned.  Works with functions that have 2 parameters.
		"""
		mapFn = self.callerInstance.matchFunction(functionName)
		if (mapFn):
			for ptr, mydict in enumerate(iterator):
	 			if ptr == 0:
					value = mydict['value']
				else:
					value = mapFn['fn'](value, mydict['value'])
					
			return value
			
 		else:
 			raise ValueError ("Error: iterMap() function wasn't given a known function: %s" % functionName)
 			
 		return None
 
 
 	def iStatBP(self, location, fastaRow):
		"""
		iStatBP(statsDict, fastaRow) -- At statsDict location, builds a list of base-pair related statistics for subsequent rows of fasta sequence data.  This "inplace" function uses statsDict in situ, so does a running total on its various stats. 
			
		Future: 'GATTCA' type buckets		
		"""	

 		if len(fastaRow) >0:
 			if not isinstance(location, dict):
 				if isinstance(location, basestring):
					(obj, key) = self.callerInstance.getNamespace(location)
					location = obj[key] # by reference
				else:
					raise ValueError ("Error: iStatBP() function wasn't given a good location for first parameter: %s" % location)
 		
			buckets = ['G','C','A','T']
			if not 'A' in location: #indicates it hasn't been initialized.
				#obj[key] = OrderedDict()
				for item in buckets:
					location[item]=0
				location['total'] = 0
			
			#Tally buckets.  Allows for N ,U, * etc. to be identified
			for char in fastaRow:
				char = char.upper()
				location[char] = (location[char] + 1) if char in location else 1 

			location['total'] += len(fastaRow)
			#Might not be at last line but calculate these anyways, in case we are:
			for item in buckets:
				location[item + '%'] = int(round(100*operator.truediv(location[item], location['total'] ) ))
				
			location['GC_content%'] = int(round(100*operator.truediv(location['G'] + location['C'], location['total'] )) )
			
		return location
 
 
	def clear(self, location):
		"""
		clear(location) -- clear out given data type.  String goes to '', number to 0, array to [], and object (and new item) to {}.
		"""	
		#location1 = self.callerInstance.namespaceSearchReplace(location)
		(obj, key) = self.callerInstance.getNamespace(location)
		value = OrderedDict() #Allows clear expression to establish a new dictionary and nickname.
		if key in obj:

			oldValue = obj[key]
		
			if isinstance(oldValue, dict):
				value = OrderedDict()
			elif isinstance(oldValue, list):
				value = []
			#Location is a literal below.  same as store(0, location). 
			elif  isinstance(oldValue, numbers.Number):
				value = 0
			elif isinstance(oldValue, basestring):
				value = ''
			#other cases?
			
		self.callerInstance.storeNamespaceValue(value, location)
		return location
		
		
	def iterFiles(self, file_name):
		"""
		iterFiles(file_name) -- Match given file_name to list of input files, and return file path.  Name can have ? and * wildcards.

		ISSUE?: Make secure by taking files/ list out of namespace area.
		Then users can't insert their own absolute file paths in.
		"""
		found = 0
		checked_files = []
		for myFile in self.callerInstance.namespace['files']:
			if fnmatch.fnmatch(myFile['name'], file_name):
				found += 1
				yield myFile
			else:
				checked_files.append(myFile['name'])
		
		# Issue, never gets to "Not found" spot?
		if found == 0:
			error_text = 'Error: unable to open any input file named like "%s". Input file list is: %s' % (file_name, str(checked_files) )
			stop_err (error_text )


	def loadFileByName(self, file_name):	
		"""
		loadFileByName(file_name) -- Iterator that returns (in a dictionary) entire contents of each file matching file_name.
		File must be supplied in input list.
		"""
		found = False
		for myFile in self.iterFiles(file_name):
			data = None
			ptr = 0
			with open(myFile['value'], 'r') as input_file_handle:
				found = True
				if myFile['type'] == "json":	
					data = json.load(input_file_handle, object_pairs_hook=OrderedDict)
				else:		
					# Text and tab-delimited		
					data = input_file_handle.read()
	
				print "Loaded %s: %s characters" % (myFile['name'], len(data) )
				yield {'value': data , 'ROW': ptr, 'name': myFile['name'] }
				ptr = ptr + 1


	def readFileByName(self, entity):
		"""
		readFileByName(entity) --  Via an iterable, read each line of file into a dictionary.
		If input entity is:
		- a string, apply iterFiles() to match to file name using glob retrieve iterable; 
		- a dictionary, read its 'value' as file path
		- otherwise assume it is an iterable file object.  
		Not applicable to reading JSON since that content has to be parsed as a whole.
		"""
		found = False
		for myFile in (self.iterFiles(entity) if isinstance(entity, basestring) else ([entity] if isinstance(entity, dict) else entity)):
			with open(myFile['value'],'r') as file_handle:
				found = True
				print "READING: ", myFile['value']
				for ptr,line in enumerate(file_handle):
					yield {'value': line.strip('\n') , 'ROW': ptr, 'name': myFile['name'] }


	def writeJsonFile(self, content, output_file_name):
		"""
		writeJsonFile(content, file_name) -- Writes given content as JSON to file_name in tool's output folder.  A link to file is provided on tool's HTML report output page.
		"""
		content = json.dumps(content, sort_keys=True, indent=4, separators=(',', ': '), default=lambda: "[unprintable iterable]")
		writeFile(self, content, output_file_name)

		
	def writeFile(self, content, output_file_name):
		"""
		writeFile(content, file_name) -- Writes given content to file_name in tool's output folder.  A link to file is provided on tool's HTML report output page.
		"""
		self.callerInstance.namespace['report_html'] += '<li><a href="%(file_name)s">%(file_name)s</a></li><br/>\n' % {'file_name': output_file_name}
		outputdir = self.callerInstance.output_folder
		output_path = os.path.join(outputdir, output_file_name)

		try:
		
			if not os.path.exists(outputdir): 
				os.makedirs(outputdir)

			with (open(output_path,'w')) as output_handle:
				# Test if content is an iterable list:
				#for line in location:
			
				if hasattr(content, '__iter__'):
					gotHeader = False
					if isinstance(content, dict):
						for (key, val) in content.iteritems():
							output_handle.write( key + '\t' + str(val) + '\n')
					else:
						for item in content:
							output_handle.write(item['value'])
				else:
					output_handle.write(content)
					
		# Helps to identify path that couldn't be written to at this level
		except OSError as e: 
			print "OS error({0}): {1}. Tried to write to {2}".format(e.errno, e.strerror, output_path)
			raise e
			
"""
POSSIBLE "LARGE FILE" REGEX IMPROVEMENT
import mmap
import re
import contextlib

pattern = re.compile(r'(\.\W+)?([^.]?nulla[^.]*?\.)',
                     re.DOTALL | re.IGNORECASE | re.MULTILINE)

with open('lorem.txt', 'r') as f:
    with contextlib.closing(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)) as m:
        for match in pattern.findall(m):
            print match[1].replace('\n', ' ')
"""

"""
ADD MORE FILE INFO

        if os.path.isfile(fp):
            n = float(os.path.getsize(fp))
            if n > 2**20:
                size = ' (%1.1f MB)' % (n/2**20)
            elif n > 2**10:
                size = ' (%1.1f KB)' % (n/2**10)
            elif n > 0:
                size = ' (%d B)' % (int(n))
        s = '%s %s' % (fpath, size)
        return s
"""
