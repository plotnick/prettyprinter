from __future__ import with_statement

class bindings(object):
    """Bind a set of variables to the given values in the dynamic scope of a
    with-statement.  The optional non-keyword argument specifies the namespace
    in which the variables are to be bound; if omitted, the global (module)
    namespace will be used."""

    def __init__(self, obj=None, **bindings):
        self.symbols = obj.__dict__ if obj else globals()
        self.bindings = bindings

    def __enter__(self):
        self.old_bindings = {}
        self.unbound = []
        for name in self.bindings:
            try:
                self.old_bindings[name] = self.symbols[name]
            except KeyError:
                self.unbound.append(name)
            self.symbols[name] = self.bindings[name]

    def __exit__(self, *exc_info):
        for name in self.old_bindings:
            self.symbols[name] = self.old_bindings[name]
        for name in self.unbound:
            del self.symbols[name]
