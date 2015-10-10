from __future__ import division, print_function, absolute_import

import types

from twisted.internet.defer import Deferred
from twisted.python.failure import Failure

from hypothesis.core import find_task, given, Return


def defer_driver(g):
    done_d = Deferred()
    if not isinstance(g, types.GeneratorType):
        done_d.callback(g)
    else:
        _iter_defer(None, g, done_d)
    return done_d


def _iter_defer(result, g, done_d):
    while True:
        try:
            if isinstance(result, Failure):
                result = result.throwExceptionIntoGenerator(g)
            else:
                result = g.send(result)
        except Return as e:
            done_d.callback(e.value)
            return
        except StopIteration:
            done_d.callback(None)
            return
        except:
            done_d.errback()
            return
        if not isinstance(result, Deferred):
            result = defer_driver(result)
        if isinstance(result, Deferred):
            result.addBoth(_iter_defer, g, done_d)
            return


def find_defer(specifier, condition, settings=None, random=None, storage=None, driver=None):
    if driver is None:
        driver = defer_driver
    return driver(find_task(specifier, condition, settings=settings, random=random))


def given_defer(*generator_arguments, **generator_kwargs):
    generator_kwargs[u'driver'] = generator_kwargs.pop(u'driver', defer_driver)
    return given(*generator_arguments, **generator_kwargs)
