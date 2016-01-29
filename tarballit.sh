#!/bin/bash
 tar -zcvf rcqc.tar.gz * --exclude "*~" --exclude "*.log" --exclude "*.pyc" --exclude "old*" --exclude "tool_test_output*" --exclude "*gz"
