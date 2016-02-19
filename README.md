# rcqc
Report Calc for Quality Control (RCQC) is an interpreter for the RCQC scripting language for text-mining log and data files to create reports and to control workflow within a workflow engine.  It works as a python command line tool and also as a Galaxy bioinformatics platform tool.  We're building a library of simple "recipe" scripts that extract quality control (QC) data from various reports like FastQC, QUAST, CheckM and SPAdes into a common JSON data format.  By placing the RCQC app in your workflow downstream from one of these apps, you can convert their textual or tabular data into a much more standardized and software-friendly format.

A second objective is to enable selected QC terms (that have been text-mined) to be marked up with their globally accessable ontology identifiers.  Currently GenEpiO, our under-development ontology, hosts key genome assembly quality control terms like "genome size ratio", contig count and various QC threshold terms.  This should be a step towards enabling pipelines to generate QC measurements that are part of the software accreditation process for adoption in commercial and public health laboratories.

See the [wiki](https://github.com/Public-Health-Bioinformatics/rcqc/wiki) for extensive documentation - especially the "Getting started" page.  Here is the command line summary:

```
Usage: rcqc.py [ruleSet file] [input files] [options]*

Records selected input text file fields into a report (json format), and
optionally applies tests to them to generate a pass/warn/fail status. Program
can be set to throw an exception based on fail states.

Options:
  -h, --help            show this help message and exit
  -v, --version         Return version of report_calc.py code.
  -H OUTPUT_HTML_FILE, --HTML=OUTPUT_HTML_FILE
                        Output HTML report to this file. (Mainly for Galaxy
                        tool use to display output folder files.)
  -f OUTPUT_FOLDER, --folder=OUTPUT_FOLDER
                        Output files (via writeFile() ) will be written to
                        this folder.  Defaults to working folder.
  -i INPUT_FILE_PATHS, --input=INPUT_FILE_PATHS
                        Provide input file information in format: [file1
                        path]:[file1 label][file1 suffix][space][file2
                        path]:[file2 label]:[file2 suffix] ... note that
                        labels can't have spaces in them.
  -o OUTPUT_JSON_FILE, --output=OUTPUT_JSON_FILE
                        Output report to this file, or to stdout if none
                        given.
  -r RULES_FILE_PATH, --rules=RULES_FILE_PATH
                        Read rules from this file.
  -e EXECUTE, --execute=EXECUTE
                        Ruleset sections to execute.
  -c CUSTOM_RULES, --custom=CUSTOM_RULES
                        Provide custom rules in addition to (or to override)
                        rules from a file.  Helpful for testing variations.
  -s SAVE_RULES_PATH, --save_rules=SAVE_RULES_PATH
                        Save modified ruleset to a file.
  -d, --debug           Provides more detail about rule execution on stdout.
  ```

This tool does require a few python modules:

pip install dateutils
pip install pyparsing

If you encounter ssl (encryption key) related problems in trying to use pip to install them, you might need to run:

pip install requests —upgrade

For the Galaxy tool these will be added as dependencies soon.
