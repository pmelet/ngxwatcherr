ngxwatcherr
===========

Python script to follow nginx error logs

Usage
=====

usage: ngxwatcherr.py [-h] [--input FILENAMES] [--period PERIOD] [--offset OFFSET] metric [metric ...]

Parse nginx error logs

positional arguments:
  metric                specification of the metric(s) to follow. Valid forms:
                        metric:spec metric:re:spec metric/spec metric/re/spec.
                        If separator is :, stat is the list of values for the
                        metric within the time; if separator is /, stat is the
                        list of values grouped by time; "metric" is typically
                        "error", "request", "client". "re" is a filter on the
                        value of the metric (ex: "timeout") but is optional.
                        "spec" is a time (1m, 10m, 1h), and is the time range
                        or granularity of the stat

optional arguments:
  -h, --help            show this help message and exit
  --input FILENAMES, -f FILENAMES
                        input file to parse. All are parsed, but only the last
                        one is followed.
  --period PERIOD, -s PERIOD
                        refresh time
  --offset OFFSET, -t OFFSET
                        time difference with log file (positive if logs are in
                        the past; negative if logs are in the future). For
                        negative time, use --offset=-2h

