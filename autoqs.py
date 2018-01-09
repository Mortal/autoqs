SAVE = 'SAVE'
SET = 'SET'
EQ = 'EQ'

class AutoAttr:
    def __init__(self, item, key):
        self._item = item
        self._key = key

    def __eq__(self, other):
        return self._item._qs.branch_on(self._key, EQ, other)


class AutoItem:
    def __init__(self, qs):
        if not isinstance(qs, AutoQueryset):
            raise TypeError(type(qs))
        self.__dict__['_qs'] = qs

    def save(self):
        self._qs.node.add_effect((SAVE, ()))

    def __getattr__(self, k):
        return AutoAttr(self, k)

    def __setattr__(self, k, v):
        self._qs.node.add_effect((SET, (k, v)))


class DecisionTree:
    comparison = None
    _effects = None
    leaf = False

    @property
    def effects(self):
        return self._effects or []

    def __repr__(self):
        effects = ''.join('%r; ' % (c,) for c in self.effects)
        if self.leaf:
            return '<DecisionTree %sLeaf>' % effects
        elif self.comparison is None:
            return '<DecisionTree %sUnexplored>' % effects
        else:
            return '<%sIF %r THEN %r ELSE %r>' % (effects, self.comparison, self.yes, self.no)

    def fully_explored(self):
        return self.leaf or (self.comparison and self.yes and self.yes.fully_explored() and self.no and self.no.fully_explored())

    def add_effect(self, effect):
        try:
            self._effects.append(effect)
        except AttributeError:
            self._effects = [effect]

    def next(self, comparison):
        if self.comparison is None:
            self.comparison = comparison
            self.yes = DecisionTree()
            self.no = DecisionTree()
            return True
        if self.comparison != comparison:
            raise Exception("Nondeterministic: %s != %s" %
                            (self.comparison, comparison))
        if not self.yes.fully_explored():
            return True
        elif not self.no.fully_explored():
            return False
        else:
            assert self.fully_explored(), (self.comparison, self.yes, self.no, self.leaf)
            raise Exception("Fully explored")


def to_python(tree):
    def visit(t, expr='qs', updates=()):
        for effect, args in t.effects:
            if effect == SAVE and updates:
                yield expr + '.update(%s)' % ', '.join('%s=%s' % (k, v) for k, v in updates)
            elif effect == SET:
                updates += (args,)
        if not t.leaf:
            k, op, target = t.comparison
            assert op == EQ
            yield from visit(t.yes, expr + '.filter(%s=%s)' % (k, target), updates)
            yield from visit(t.no, expr + '.exclude(%s=%s)' % (k, target), updates)

    return '\n'.join(visit(tree))


class AutoQueryset:
    def __init__(self):
        self.root = DecisionTree()

    def __iter__(self):
        self.node = None
        return self

    def __next__(self):
        if self.node is not None:
            self.node.leaf = True
        self.node = self.root
        if self.node.fully_explored():
            raise StopIteration
        return AutoItem(self)

    def branch_on(self, item_key, op, target):
        if self.node.next((item_key, op, target)):
            self.node = self.node.yes
            return True
        else:
            self.node = self.node.no
            return False

    def __enter__(self):
        return self

    def __exit__(self, exc, exv, ext):
        pass


def test():
    with AutoQueryset() as qs:
        for o in qs:
            if o.a == 1:
                if o.b == 1:
                    o.m = 2
                else:
                    o.m = 4
                o.save()
            else:
                o.m = 3
                o.save()
    print(repr(qs.root))
    print(to_python(qs.root))

    # UPDATE t SET m = 2 WHERE n = 1

    # x = qs.filter(a=1)
    # x.filter(b=1).update
    # qs.filter(n=1).update(m=2)
    # qs.exclude(n=1).update(m=3)


if __name__ == '__main__':
    test()
