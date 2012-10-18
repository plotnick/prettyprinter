from __future__ import with_statement
import timeit

setup = """
import pprint
import prettyprinter as pp
from format import format, parse_control_string

null = open("/dev/null", "w")
tupler = "(~{~A,~^ ~@{~A~^, ~}~})"
l = tuple(xrange(1000))
d = dict(zip(range(100), range(100, 200)))
"""[1:]
stmts = (("parse", """tuple(parse_control_string(tupler))"""),
         ("format", """format(null, "~~foo: ~D pon~:@P~%", 3)"""),
         ("iteration", """format(null, tupler, l)"""),
         ("prettyprinter", """pp.pprint(l, stream=null)"""),
         ("pprint", """pprint.pprint(l, null)"""))
for name, stmt in stmts:
    print ">> %s" % name
    timeit.main(["-s", setup, stmt])
    print

