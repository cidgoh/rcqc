#!/bin/bash
 tar -zcvf report_calc.tar.gz * --exclude "*~" --exclude "*.pyc" --exclude "old*" --exclude "tool_test_output*" --exclude "*gz"
