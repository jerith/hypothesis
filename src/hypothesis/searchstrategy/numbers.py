# coding=utf-8

# Copyright (C) 2013-2015 David R. MacIver (david@drmaciver.com)

# This file is part of Hypothesis (https://github.com/DRMacIver/hypothesis)

# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at http://mozilla.org/MPL/2.0/.

# END HEADER

from __future__ import division, print_function, absolute_import, \
    unicode_literals

import sys
import math
import struct
from random import Random

import hypothesis.params as params
import hypothesis.descriptors as descriptors
import hypothesis.internal.utils.distributions as dist
from hypothesis.internal.compat import hrange, integer_types
from hypothesis.searchstrategy.misc import SampledFromStrategy
from hypothesis.searchstrategy.strategy import BadData, SearchStrategy, \
    MappedSearchStrategy, check_type, check_data_type

from .table import strategy_for, strategy_for_instances


class IntStrategy(SearchStrategy):

    """A generic strategy for integer types that provides the basic methods
    other than produce.

    Subclasses should provide the produce method.

    """
    descriptor = int

    def from_basic(self, data):
        check_data_type(integer_types, data)
        return data

    def to_basic(self, template):
        return template

    def simplify(self, x):
        ix = int(x)
        if type(ix) != type(x):  # pragma: no cover
            yield ix
        if x < 0:
            yield -x
            for y in self.simplify(-x):
                yield -y
        elif x > 0:
            yield 0
            if x == 1:
                return
            yield x // 2
            if x == 2:
                return
            max_iters = 100
            if x <= max_iters:
                for i in hrange(x - 1, 0, -1):
                    if i != x // 2:
                        yield i
            else:
                random = Random(x)
                seen = {0, x // 2}
                for _ in hrange(max_iters):
                    i = random.randint(0, x - 1)
                    if i not in seen:
                        yield i
                    seen.add(i)


class RandomGeometricIntStrategy(IntStrategy):

    """A strategy that produces integers whose magnitudes are a geometric
    distribution and whose sign is randomized with some probability.

    It will tend to be biased towards mostly negative or mostly
    positive, and the size of the integers tends to be biased towards
    the small.

    """
    parameter = params.CompositeParameter(
        negative_probability=params.BetaFloatParameter(0.5, 0.5),
        p=params.BetaFloatParameter(alpha=0.2, beta=1.8),
    )

    def produce_template(self, random, parameter):
        value = dist.geometric(random, parameter.p)
        if dist.biased_coin(random, parameter.negative_probability):
            value = -value
        return value


class BoundedIntStrategy(SearchStrategy):

    """A strategy for providing integers in some interval with inclusive
    endpoints."""

    parameter = params.CompositeParameter()

    def __init__(self, start, end):
        SearchStrategy.__init__(self)
        self.descriptor = descriptors.integers_in_range(start, end)
        self.start = start
        self.end = end
        if start > end:
            raise ValueError('Invalid range [%d, %d]' % (start, end))
        self.parameter = params.NonEmptySubset(
            tuple(range(start, end + 1)),
            activation_chance=min(0.5, 3.0 / (end - start + 1))
        )
        self.size_lower_bound = end - start + 1
        self.size_upper_bound = end - start + 1

    def from_basic(self, data):
        check_data_type(integer_types, data)
        return data

    def to_basic(self, template):
        return template

    def produce_template(self, random, parameter):
        if self.start == self.end:
            return self.start
        return random.choice(parameter)

    def simplify(self, x):
        if x == self.start:
            return
        for t in hrange(x - 1, self.start - 1, -1):
            yield t
        mid = (self.start + self.end) // 2
        if x > mid:
            yield self.start + (self.end - x)
            for t in hrange(x + 1, self.end + 1):
                yield t


class FloatStrategy(SearchStrategy):

    """Generic superclass for strategies which produce floats."""
    descriptor = float

    def __init__(self):
        SearchStrategy.__init__(self)
        self.int_strategy = RandomGeometricIntStrategy()

    def to_basic(self, value):
        check_type(float, value)
        return (
            struct.unpack(b'!Q', struct.pack(b'!d', value))[0]
        )

    def from_basic(self, value):
        check_type(integer_types, value)
        try:
            return (
                struct.unpack(b'!d', struct.pack(b'!Q', value))[0]
            )
        except (struct.error, ValueError, OverflowError) as e:
            raise BadData(e.args[0])

    def simplify(self, x):
        if x == 0.0:
            return
        if math.isnan(x):
            yield 0.0
            yield float('inf')
            yield -float('inf')
            return
        if math.isinf(x):
            yield math.copysign(
                sys.float_info.max, x
            )
            return

        if x < 0:
            yield -x

        yield 0.0
        try:
            n = int(x)
            y = float(n)
            if x != y:
                yield y
            for m in self.int_strategy.simplify(n):
                yield x + (m - n)
        except (ValueError, OverflowError):
            pass
        if abs(x) > 1.0:
            yield x / 2


class WrapperFloatStrategy(FloatStrategy):

    def __init__(self, sub_strategy):
        super(WrapperFloatStrategy, self).__init__()
        self.sub_strategy = sub_strategy
        self.parameter = sub_strategy.parameter

    def produce_template(self, random, pv):
        return self.sub_strategy.reify(
            self.sub_strategy.produce_template(random, pv))


class JustIntFloats(FloatStrategy):

    def __init__(self, int_strategy):
        super(JustIntFloats, self).__init__()
        self.int_strategy = int_strategy
        self.parameter = self.int_strategy.parameter

    def produce_template(self, random, pv):
        return float(self.int_strategy.produce_template(random, pv))


def compose_float(sign, exponent, fraction):
    as_long = (sign << 63) | (exponent << 52) | fraction
    return struct.unpack(b'!d', struct.pack(b'!Q', as_long))[0]


class FullRangeFloats(FloatStrategy):
    parameter = params.CompositeParameter(
        negative_probability=params.UniformFloatParameter(0, 1),
        subnormal_probability=params.UniformFloatParameter(0, 0.5),
    )

    def produce_template(self, random, pv):
        sign = int(dist.biased_coin(random, pv.negative_probability))
        if dist.biased_coin(random, pv.subnormal_probability):
            exponent = 0
        else:
            exponent = random.getrandbits(11)

        return compose_float(
            sign,
            exponent,
            random.getrandbits(52)
        )


def _find_max_exponent():
    """Returns the largest n such that math.ldexp(1.0, -n) > 0"""
    upper = 1
    while math.ldexp(1.0, -upper) > 0:
        lower = upper
        upper *= 2
    assert math.ldexp(1.0, -lower) > 0
    assert math.ldexp(1.0, -upper) == 0
    assert upper > lower + 1
    while upper > lower + 1:
        mid = (upper + lower) // 2
        if math.ldexp(1.0, -mid) > 0:
            lower = mid
        else:
            upper = mid
    return lower


class SmallFloats(FloatStrategy):
    max_exponent = _find_max_exponent()
    parameter = params.CompositeParameter(
        negative_probability=params.UniformFloatParameter(0, 1),
        min_exponent=params.UniformIntParameter(0, max_exponent)
    )

    def produce_template(self, random, pv):
        base = math.ldexp(
            random.random(),
            -random.randint(pv.min_exponent, self.max_exponent)
        )
        if dist.biased_coin(random, pv.negative_probability):
            base = -base
        return base


class FixedBoundedFloatStrategy(FloatStrategy):

    """A strategy for floats distributed between two endpoints.

    The conditional distribution tries to produce values clustered
    closer to one of the ends.

    """
    descriptor = float

    parameter = params.CompositeParameter(
        cut=params.UniformFloatParameter(0, 1),
        leftwards=params.BiasedCoin(0.5),
    )

    def __init__(self, lower_bound, upper_bound):
        SearchStrategy.__init__(self)
        self.lower_bound = float(lower_bound)
        self.upper_bound = float(upper_bound)

    def produce_template(self, random, pv):
        if pv.leftwards:
            left = self.lower_bound
            right = pv.cut
        else:
            left = pv.cut
            right = self.upper_bound
        return left + random.random() * (right - left)

    def simplify(self, value):
        if value == self.lower_bound:
            return
        yield self.lower_bound
        if value == self.upper_bound:
            return
        yield self.upper_bound
        mid = (self.lower_bound + self.upper_bound) * 0.5
        if value == mid:
            return
        yield mid


class BoundedFloatStrategy(FloatStrategy):

    """A float strategy such that every conditional distribution is bounded but
    the endpoints may be arbitrary."""

    def __init__(self):
        super(BoundedFloatStrategy, self).__init__()
        self.inner_strategy = FixedBoundedFloatStrategy(0, 1)
        self.parameter = params.CompositeParameter(
            left=params.NormalParameter(0, 1),
            length=params.ExponentialParameter(1),
            spread=self.inner_strategy.parameter,
        )

    def produce_template(self, random, pv):
        return pv.left + self.inner_strategy.produce_template(
            random, pv.spread
        ) * pv.length


class GaussianFloatStrategy(FloatStrategy):

    """A float strategy such that every conditional distribution is drawn from
    a gaussian."""
    parameter = params.CompositeParameter(
        mean=params.NormalParameter(0, 1),
    )

    def produce_template(self, random, pv):
        return random.normalvariate(pv.mean, 1)


class ExponentialFloatStrategy(FloatStrategy):

    """
    A float strategy such that every conditional distribution is of the form
    aX + b where a = +/- 1 and X is an exponentially distributed random
    variable.
    """
    parameter = params.CompositeParameter(
        lambd=params.GammaParameter(2, 50),
        zero_point=params.NormalParameter(0, 1),
        negative=params.BiasedCoin(0.5),
    )

    def produce_template(self, random, pv):
        value = random.expovariate(pv.lambd)
        if pv.negative:
            value = -value
        return pv.zero_point + value


class NastyFloats(FloatStrategy, SampledFromStrategy):

    def __init__(self):
        SampledFromStrategy.__init__(
            self,
            descriptor=float,
            elements=[
                0.0,
                sys.float_info.min,
                -sys.float_info.min,
                float('inf'),
                -float('inf'),
                float('nan'),
            ]
        )


class ComplexStrategy(MappedSearchStrategy):

    """A strategy over complex numbers, with real and imaginary values
    distributed according to some provided strategy for floating point
    numbers."""

    def pack(self, value):
        return complex(*value)


@strategy_for_instances(descriptors.IntegerRange)
def define_stragy_for_integer_Range(strategies, descriptor):
    return BoundedIntStrategy(descriptor.start, descriptor.end)


@strategy_for_instances(descriptors.FloatRange)
def define_strategy_for_float_Range(strategies, descriptor):
    return FixedBoundedFloatStrategy(descriptor.start, descriptor.end)


strategy_for(int)(
    RandomGeometricIntStrategy())


@strategy_for(float)
def define_float_strategy(strategies, descriptor):
    return WrapperFloatStrategy(
        GaussianFloatStrategy() |
        BoundedFloatStrategy() |
        ExponentialFloatStrategy() |
        JustIntFloats(strategies.strategy(int)) |
        NastyFloats() |
        NastyFloats() |
        FullRangeFloats() |
        SmallFloats()
    )


@strategy_for(complex)
def define_complex_strategy(strategies, descriptor):
    return ComplexStrategy(complex, strategies.strategy((float, float)))