#! /usr/bin/python

import sys, re, curses, operator, time, signal, math, os, os.path
from datetime import datetime, timedelta
from collections import defaultdict


def follow(thefile, sleep=1, after=None, before=None):
	new_data = False
	while True:
		line = thefile.readline()
		if not line: 
			if after and new_data:
				after()
			new_data = False
			time.sleep(sleep)
		else: 
			if before and not new_data:
				# callback before data arrives
				before()
			new_data = True
			yield line


def sum_dict(d, u):
	maxkey = 0
	for k,v in u.iteritems(): 
		maxkey = max(maxkey,k)
		d[k] += v
	return maxkey

class AllStats(object):
	def __init__(self):
		self.data = defaultdict(lambda:Stats())

	def append(self, data, time):
		for key, value in data.iteritems():
			#print "'%s'"%(key)
			self.data[key].append(value, time)

	def clear(self):
		for key, _ in self.data.iteritems():
			self.data[key].clear()

	def keys(self):
		return self.data.keys()

	def __getitem__(self, key):
		return self.data.get(key)

class Stats(object):
	def __init__(self):
		self.data = defaultdict(lambda:Stat())
		self.clear()
	
	def append(self, key, time):
		self.data[key].append(time)
		self.last_keys.add(key)

	def last(self, delta=None, offset=None, max=None, vfilter=None):
		keys = filter(operator.itemgetter(1), 
			          sorted([(key,value.last(delta,offset)) for key,value in self.data.iteritems() 
			          	                                     if vfilter is None or re.search(vfilter,key) is not None], 
			          	     key=operator.itemgetter(1), 
			          	     reverse=True))
		if max:
			return keys[:max]
		return keys

	def group(self, delta, offset=None, max=None, vfilter=None):
		stat = defaultdict(lambda:0)
		maxkey = 0
		for key,value in self.data.iteritems():
			if vfilter is None or re.search(vfilter,key) is not None:
				vstat = value.group(delta=delta, offset=offset)
				maxkey = sum_dict(stat,vstat)
		for i in range(maxkey):
			stat[i] += 0 #trick

		return sorted([(v,delta*k) for k,v in stat.iteritems()], key=operator.itemgetter(1))	

	def clear(self):
		self.last_keys = set()

	def is_recent(self, key):
		return key in self.last_keys

	def __getitem__(self, key):
		return self.data.get(key)

class Stat(object):
	def __init__(self):
		self.data = []

	def append(self, time):
		self.data.append(time)

	def last(self, delta=None, offset=None):
		if not delta:
			return len(self)
		count = 0
		now = datetime.now()
		if offset:
			now = now - offset
		for time in reversed(self.data):
			#print time, time + delta, now
			if time + delta < now:
				break
			count += 1	
		return count

	def group(self, delta, offset=None):
		res = defaultdict(lambda:0)
		gr = delta.total_seconds()
		now = datetime.now()
		if offset:
			now = now - offset
		for time in reversed(self.data):
			d = (now-time).total_seconds()
			#print >>sys.stderr, time, now, d, d // gr
			res[int(d//gr)] += 1
		return res

	def __len__(self):
		return len(self.data)


ERRORS_RE = '^(.*) \[(.*)\] ([0-9#]+): ([0-9*]+) (.*)'
BASE_STAT = "error"

errors_stats = AllStats()

def add_stats(error, time, data):
	data[BASE_STAT] = error
	errors_stats.append(data, time)


class WindowManager(object):
	def __init__(self, windows=[]):
		self.screen = curses.initscr()
		curses.noecho()
		curses.cbreak()
		curses.start_color()
		self.screen.keypad(1)

		self.windows = windows
		self.setup()

	def setup(self):
		(ROW, COL) = self.screen.getmaxyx()

		colcount = int(math.floor(math.sqrt(len(self.windows))))
		rowcount = int(math.ceil(float(len(self.windows)) / colcount))
		colwidth = int(COL // colcount)
		rowheight = int(ROW // rowcount)
		print colcount, rowcount, colwidth, rowheight

		for i,window in enumerate(self.windows):
			window.setup(i//colcount, 
				         i%colcount,
				         rowcount,
				         colcount,
				         rowheight,
				         colwidth,
				         i == len(self.windows)-1)
			window.display()


class Window(object):
	def __init__(self):
		self.data = None
		self.title = None
		self.format = None
		self.window = None

	def setup(self, row, col, nbrows, nbcols, rowh, colw, lastcell):
		self.col = col
		self.row = row
		self.nbrows = nbrows
		self.nbcols = nbcols
		self.lastcell = lastcell
		
		beg_col = col * colw
		beg_row = row * rowh
		if self.lastcell and not self.lastcol:
			colw += 1
		self.width = colw
		self.height = rowh
		
		self.window = curses.newwin(rowh, colw, beg_row, beg_col)

		self.border = [
			self.l_border,
			self.r_border,
			self.t_border,
			self.b_border,
			self.tl_border,
			self.tr_border,
			self.bl_border,
			self.br_border,
		]

	@property
	def l_border(self):
		return curses.ACS_VLINE
	
	@property
	def r_border(self):
	    return curses.ACS_VLINE if self.lastcol or self.lastcell else ' '

	@property
	def t_border(self):
		return curses.ACS_HLINE if self.row == 0 else ' '

	@property
	def b_border(self):
		return curses.ACS_HLINE

	@property
	def tl_border(self):
		if self.row == 0 and self.col == 0:
			return curses.ACS_ULCORNER 
		if self.row == 0:
			return curses.ACS_TTEE
		return curses.ACS_VLINE

	@property
	def tr_border(self):
		if self.row == 0:
			if self.lastcol:
				return curses.ACS_URCORNER	
			return curses.ACS_HLINE
		if self.lastcol or self.lastcell:
			return curses.ACS_VLINE
		return ' '

	@property
	def bl_border(self):
		if self.lastrow:
			if self.col == 0:
				return curses.ACS_LLCORNER
			return curses.ACS_BTEE
		if self.col == 0:
			return curses.ACS_LTEE
		return curses.ACS_PLUS

	@property
	def br_border(self):
		if self.lastcell:
			return curses.ACS_LRCORNER
		if self.lastcol:
			return curses.ACS_RTEE
		return curses.ACS_HLINE

	@property
	def vertical_offset(self):
		return 1 if self.row == 0 else 0

	@property
	def lastcol(self):
	    return self.col == self.nbcols-1

	@property
	def lastrow(self):
	    return self.row == self.nbrows-1 

	def display(self):
		if self.window is None:
			# not ready ?
			return
		#self.window.clear()
		self.window.border(*self.border)
		if self.title:
			self._center(self.title, 
				         self.vertical_offset, 
				         curses.A_REVERSE)
		if self.data:
			for i,data in enumerate(self.data[:self.viewport_height]):
				self.window.addnstr(i + self.vertical_offset + 1,
					                1,
					                self.format % (data.get("data")), 
					                self.viewport_width, 
					                data.get("attr"))
		self.window.refresh()
	
	def _center(self, str, row, attr=None):
		tab = (self.viewport_width - len(self.title)) // 2
		title = "%s%s%s" % (' '*tab, self.title, ' '*(self.viewport_width-len(self.title)-tab))
		self.window.addnstr(row, 
			                1, 
			                title, 
			                self.viewport_width, 
			                attr)

	def setTitle(self, title):
		self.title = title
		self.display()

	def setList(self, data, fmt):
		self.data = data		
		self.format = fmt
		self.display()

	@property
	def viewport_width(self):
	    return self.width - (2 if self.lastcol or self.lastcell else 1)

	@property
	def viewport_height(self):
	    return self.height - (3 if self.row==0 else 2)
	


wm = None

def init_display(displays):
	signal.signal(signal.SIGINT, close_display)
	#signal.signal(signal.SIGINT, signal.SIG_IGN)

	windows = []
	for display in displays:
		display["window"] = Window()
		windows.append(display["window"])

	wm = WindowManager(windows)


def close_display(signal=None, frame=None, error=None):
	curses.nocbreak()
	curses.echo()
	curses.endwin()
	if error:
		print >>sys.stderr, error.message
		import traceback
		traceback.print_exc(file=sys.stderr)
	print >>sys.stderr, "\n".join(errors_stats.keys())
	sys.exit(0)


def update_display(displays, offset):
	for display in displays:
		stat = display["stat"]
		stat_type = display.get("type")
		data = []
		stats = errors_stats[stat]
		if stats:
			if stat_type == 'histogram':
				if "re" in display:
					display["window"].setTitle("%s / %s (each %s)" % (stat, display.get("re"), str(display["delta"])))
				else:
					display["window"].setTitle("%s (each %s)" % (stat, str(display["delta"])))
				groups = stats.group(delta=display["delta"], 
					                           vfilter=display.get("re"), 
		                                       offset=offset, 
		                                       max=display["window"].viewport_height)
				if groups:
					for (key,count) in groups:
						data.append({ "data":(count,key), "attr": 0 })
				display["window"].setList(data, "%16s  %s")
			else:
				if "re" in display:
					display["window"].setTitle("%s / %s (last %s)" % (stat, display.get("re"), str(display["delta"])))
				else:
					display["window"].setTitle("%s (last %s)" % (stat, str(display["delta"])))
					
				for (key,count) in stats.last(delta=display["delta"], 
					                          vfilter=display.get("re"), 
		                                      offset=offset, 
		                                      max=display["window"].viewport_height):
					data.append({ "data":(count,key), 
						          "attr": curses.A_BOLD if stats.is_recent(key) else 0 })
				display["window"].setList(data, "%3d  %s")
		

def new_data_arrived():
	errors_stats.clear()

def treat_one_line(line, displays):
	line = line.strip()
	(time, etype, _, _, pline) = re.match(ERRORS_RE,line).groups()
	pline = re.split("\s*,\s*",pline.strip())
	options = dict(map(lambda x:x.groups(),
	                   filter(lambda x:x is not None,
	                          [re.match("([a-z]+)\s*:\s*\"?(.+)\"?\s*",x) for x in pline])))

	add_stats(pline[0], datetime.strptime(time,"%Y/%m/%d %H:%M:%S"), options)

def follow_log_file(f, displays, sleep, offset):
	for line in follow(f, 
		               sleep, 
		               lambda:update_display(displays, offset), 
		               new_data_arrived):
		treat_one_line(line, displays)

def parse_log_file(f, displays, sleep, offset):
	for line in f.readlines():
		treat_one_line(line, displays)

timedesc = [
	{ "re" : "([-+0-9]+)s[a-z]*", "number": 1, "arg": "seconds" },
	{ "re" : "([-+0-9]+)m[a-z]*", "number": 1, "arg": "minutes" },
	{ "re" : "([-+0-9]+)h[a-z]*", "number": 1, "arg": "hours" },
	{ "re" : "([-+0-9]+)d[a-z]*", "number": 1, "arg": "days" },
	{ "re" : "([-+0-9]+)", "number": 1, "arg": "hours" },
]

def get_time_delta( timestr ):
	for desc in timedesc:
		match = re.match(desc["re"], timestr)
		if match:
			timedelta_args = { desc["arg"]: int(match.group(desc["number"])) }
			return timedelta(**timedelta_args)


def parse_arguments(args):
	displays = []
	for metric in args.metrics:
		t = re.split("[:/]",metric)
		tp = "histogram" if '/' in metric else "list"
		if len(t) == 3:
			m, r, s = t
		elif len(t) == 2:
			(m, s), r = t, None
		#print t, m, s, r, tp
		delta = get_time_delta(s)
		if delta is not None:
			displays.append( { "delta": delta, "stat": m, "re": r, "type": tp } )
		else:
			print >>sys.stderr, "Metric '%s' cannot be parsed" % (metric)

	offset = None
	if args.offset:
		offset = get_time_delta(args.offset)

	period = 1
	if args.period:
		period = max(args.period, period)

	filenames = []
	if args.filenames:
		for filename in args.filenames:
			if os.path.exists(filename):
				filenames.append(filename)
	else:
		print >>sys.stderr, "File", args.filenames, "does not exist"

	return displays, filenames, period, offset

if __name__ == '__main__':

	import argparse
	parser = argparse.ArgumentParser(description='Parse nginx error logs')
	parser.add_argument('--input', '-f', 
		                dest='filenames', 
		                action='append',
	                    default=[],
	                    help='input file to parse. All are parsed, but only the last one is followed.')
	parser.add_argument('--period', '-s', 
		                dest='period', 
		                action='store',
	                    default="1",
	                    type=int,
	                    help='refresh time')
	parser.add_argument('--offset', '-t', 
		                dest='offset', 
		                action='store',
	                    default="0",
	                    help='time difference with log file (positive if logs are in the past; negative if logs are in the future). For negative time, use --offset=-2h')
	
	parser.add_argument('metrics', 
		                metavar='metric', 
		                type=str, 
		                nargs='+',
                        help='''specification of the metric(s) to follow. 
                                Valid forms: metric:spec metric:re:spec metric/spec metric/re/spec. 
                                If separator is :, stat is the list of values for the metric within the time;
                                if separator is /, stat is the list of values grouped by time;
                                "metric" is typically "error", "request", "client".
                                "re" is a filter on the value of the metric (ex: "timeout") but is optional.
                                "spec" is a time (1m, 10m, 1h), and is the time range or granularity of the stat''')

	args = parser.parse_args()
	print >>sys.stderr, args

	displays, filenames, period, offset = parse_arguments(args)
	print >>sys.stderr, filenames, period, offset

	if len(filenames):
		init_display(displays)
		try:
			for filename in filenames[:-1]:
				errors = open(filename)
				parse_log_file(errors, displays, period, offset)
			errors = open(filenames[-1])
			follow_log_file(errors, displays, period, offset)
		except Exception as e:
			close_display(error=e)


