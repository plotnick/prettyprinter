from __future__ import with_statement

class bindings(object):
    """Bind a set of variables to the given values in the dynamic scope of a
    with-statement.  The optional non-keyword argument specifies the namespace
    in which the variables are to be bound; if omitted, the global (module)
    namespace will be used."""

    def __init__(self, obj=None, **bindings):
        self.namespace = obj and obj.__dict__
        self.bindings = bindings

    def __enter__(self):
        syms = self.namespace or globals()
        self.old_bindings = []
        self.unbound = []
        for name, value in self.bindings.items():
            try:
                self.old_bindings.append((name, syms[name]))
            except KeyError:
                self.unbound.append(name)
            syms[name] = value

    def __exit__(self, *exc_info):
        syms = self.namespace or globals()
        for name, value in self.old_bindings:
            syms[name] = value
        for name in self.unbound:
            del syms[name]
