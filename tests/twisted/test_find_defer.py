# coding=utf-8

# This file is part of Hypothesis (https://github.com/DRMacIver/hypothesis)

# Most of this work is copyright (C) 2013-2015 David R. MacIver
# (david@drmaciver.com), but it contains contributions by others. See
# https://github.com/DRMacIver/hypothesis/blob/master/CONTRIBUTING.rst for a
# full list of people who may hold copyright, and consult the git log if you
# need to determine who owns an individual contribution.

# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at http://mozilla.org/MPL/2.0/.

# END HEADER

from __future__ import division, print_function, absolute_import

import math
from functools import wraps

import pytest
from hypothesis import Settings
from hypothesis.errors import Timeout, NoSuchExample, \
    DefinitelyNoSuchExample
from hypothesis.extra.twisted import find_defer
from hypothesis.strategies import lists, floats, booleans, integers, \
    streaming, dictionaries
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks
from twisted.internet.task import deferLater
from twisted.trial.unittest import TestCase


def async(func, delay=0):
    @wraps(func)
    def wrapped(*args, **kw):
        return deferLater(reactor, delay, func, *args, **kw)
    return wrapped


class TestFindDefer(TestCase):
    @inlineCallbacks
    def test_can_find_an_int_sync(self):
        any_int = yield find_defer(integers(), lambda x: True)
        assert any_int == 0
        biggish_int = yield find_defer(integers(), lambda x: x >= 13)
        assert biggish_int == 13

    @inlineCallbacks
    def test_can_find_an_int(self):
        any_int = yield find_defer(integers(), async(lambda x: True))
        assert any_int == 0
        biggish_int = yield find_defer(integers(), async(lambda x: x >= 13))
        assert biggish_int == 13

    @inlineCallbacks
    def test_can_find_an_int_slow(self):
        any_int = yield find_defer(
            integers(), async(lambda x: True, delay=0.01))
        assert any_int == 0
        biggish_int = yield find_defer(
            integers(), async(lambda x: x >= 13, delay=0.01))
        assert biggish_int == 13

    @inlineCallbacks
    def test_can_find_list(self):
        x = yield find_defer(lists(integers()), async(lambda x: sum(x) >= 10))
        assert sum(x) == 10

    @inlineCallbacks
    def test_can_find_nan(self):
        yield find_defer(floats(), async(math.isnan))

    @inlineCallbacks
    def test_can_find_nans(self):
        x = yield find_defer(
            lists(floats()), async(lambda x: math.isnan(sum(x))))
        if len(x) == 1:
            assert math.isnan(x[0])
        else:
            assert 2 <= len(x) <= 3

    @inlineCallbacks
    def test_find_streaming_int(self):
        n = 100
        r = yield find_defer(
            streaming(integers()), async(lambda x: all(t >= 1 for t in x[:n])))
        assert list(r[:n]) == [1] * n

    @inlineCallbacks
    def test_raises_when_no_example(self):
        settings = Settings(
            max_examples=20,
            min_satisfying_examples=0,
        )
        with pytest.raises(NoSuchExample):
            yield find_defer(
                integers(), async(lambda x: False), settings=settings)

    @inlineCallbacks
    def test_raises_more_specifically_when_exhausted(self):
        with pytest.raises(DefinitelyNoSuchExample):
            yield find_defer(booleans(), async(lambda x: False))

    @inlineCallbacks
    def test_condition_is_name(self):
        settings = Settings(
            max_examples=20,
            min_satisfying_examples=0,
        )

        @async
        def bad(x):
            return False

        with pytest.raises(NoSuchExample) as e:
            yield find_defer(integers(), bad, settings=settings)
        assert u'bad' in e.value.args[0]

    @inlineCallbacks
    def test_find_dictionary(self):
        keys_gt_values = yield find_defer(
            dictionaries(keys=integers(), values=integers()),
            async(lambda xs: any(kv[0] > kv[1] for kv in xs.items())))
        assert len(keys_gt_values) == 1

    @inlineCallbacks
    def test_times_out(self):
        with pytest.raises(Timeout) as e:
            yield find_defer(
                integers(),
                async(lambda x: False, delay=0.05),
                settings=Settings(timeout=0.01))

        e.value.args[0]
