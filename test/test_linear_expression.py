#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Mar 17 17:06:36 2021

@author: fabian
"""

import pandas as pd
import pytest
import xarray as xr
from xarray.testing import assert_equal

from linopy import LinearExpression, Model, merge

m = Model()

x = m.add_variables(pd.Series([0, 0]), 1, name="x")
y = m.add_variables(4, pd.Series([8, 10]), name="y")
z = m.add_variables(0, pd.DataFrame([[1, 2], [3, 4], [5, 6]]).T, name="z")
v = m.add_variables(coords=[pd.RangeIndex(20, name="dim_2")], name="v")


def test_repr():
    expr = m.linexpr((10, "x"), (1, "y"))
    expr.__repr__()
    expr._repr_html_()


def test_values():
    expr = m.linexpr((10, "x"), (1, "y"))
    target = xr.DataArray(
        [[10, 1], [10, 1]], coords={"dim_0": [0, 1]}, dims=["dim_0", "_term"]
    )
    assert_equal(expr.coeffs, target)


def test_duplicated_index():
    expr = m.linexpr((10, "x"), (-1, "x"))
    assert (expr._term == [0, 1]).all()


def test_variable_to_linexpr():
    expr = 1 * x
    assert isinstance(expr, LinearExpression)
    assert expr.nterm == 1
    assert len(expr.vars.dim_0) == x.shape[0]

    expr = x * 1
    assert isinstance(expr, LinearExpression)

    expr = 10 * x + y
    assert isinstance(expr, LinearExpression)
    assert_equal(expr, m.linexpr((10, "x"), (1, "y")))

    expr = x + 8 * y
    assert isinstance(expr, LinearExpression)
    assert_equal(expr, m.linexpr((1, "x"), (8, "y")))

    expr = x + y
    assert isinstance(expr, LinearExpression)
    assert_equal(expr, m.linexpr((1, "x"), (1, "y")))

    expr = x - y
    assert isinstance(expr, LinearExpression)
    assert_equal(expr, m.linexpr((1, "x"), (-1, "y")))

    expr = -x - 8 * y
    assert isinstance(expr, LinearExpression)
    assert_equal(expr, m.linexpr((-1, "x"), (-8, "y")))

    expr = x.sum()
    assert isinstance(expr, LinearExpression)

    with pytest.raises(TypeError):
        x + 10
    with pytest.raises(TypeError):
        x - 10


def test_expr_to_anonymous_constraint():
    expr = 10 * x + y
    con = expr <= 10
    assert isinstance(con.lhs, LinearExpression)
    assert con.sign.item() == "<="
    assert con.rhs.item() == 10


def test_add():

    expr = 10 * x + y
    other = 2 * y + z
    res = expr + other

    assert res.nterm == expr.nterm + other.nterm
    assert (res.coords["dim_0"] == expr.coords["dim_0"]).all()
    assert (res.coords["dim_1"] == other.coords["dim_1"]).all()
    assert res.notnull().all().to_array().all()

    assert isinstance(x - expr, LinearExpression)
    assert isinstance(x + expr, LinearExpression)

    with pytest.raises(TypeError):
        expr + 10
    with pytest.raises(TypeError):
        expr - 10


def test_sub():
    expr = 10 * x + y
    other = 2 * y - z
    res = expr - other

    assert res.nterm == expr.nterm + other.nterm
    assert (res.coords["dim_0"] == expr.coords["dim_0"]).all()
    assert (res.coords["dim_1"] == other.coords["dim_1"]).all()
    assert res.notnull().all().to_array().all()


def test_sum():
    expr = 10 * x + y + z
    res = expr.sum("dim_0")

    assert res.size == expr.size
    assert res.nterm == expr.nterm * len(expr.dim_0)

    res = expr.sum()
    assert res.size == expr.size
    assert res.nterm == expr.size
    assert res.notnull().all().to_array().all()

    assert_equal(expr.sum(["dim_0", "_term"]), expr.sum("dim_0"))


def test_merge():
    expr1 = (10 * x + y).sum("dim_0")
    expr2 = z.sum("dim_0")

    res = merge(expr1, expr2)
    assert res._term.size == 6

    res = merge([expr1, expr2])
    assert res._term.size == 6

    # now concat with same length of terms
    expr1 = z.sel(dim_0=0).sum("dim_1")
    expr2 = z.sel(dim_0=1).sum("dim_1")

    res = merge(expr1, expr2, dim="dim_1")
    assert res.nterm == 3

    # now with different length of terms
    expr1 = z.sel(dim_0=0, dim_1=slice(0, 1)).sum("dim_1")
    expr2 = z.sel(dim_0=1).sum("dim_1")

    res = merge(expr1, expr2, dim="dim_1")
    assert res.nterm == 3
    assert res.sel(dim_1=0, _term=2).vars.item() == -1


def test_sum_drop_zeros():
    coeff = xr.zeros_like(z)
    coeff[1, 0] = 3
    coeff[0, 2] = 5
    expr = coeff * z

    res = expr.sum("dim_0", drop_zeros=True)
    assert res.nterm == 1

    res = expr.sum("dim_1", drop_zeros=True)
    assert res.nterm == 1

    coeff[1, 2] = 4
    res = expr.sum()

    res = expr.sum("dim_0", drop_zeros=True)
    assert res.nterm == 2

    res = expr.sum("dim_1", drop_zeros=True)
    assert res.nterm == 2


def test_mul():
    expr = 10 * x + y + z
    mexpr = expr * 10
    assert (mexpr.coeffs.sel(dim_1=0, dim_0=0, _term=0) == 100).item()

    mexpr = 10 * expr
    assert (mexpr.coeffs.sel(dim_1=0, dim_0=0, _term=0) == 100).item()


def test_sanitize():
    expr = 10 * x + y + z
    assert isinstance(expr.sanitize(), LinearExpression)


def test_group_terms():
    groups = xr.DataArray([1] * 10 + [2] * 10, coords=v.coords)
    grouped = v.to_linexpr().group_terms(groups)
    assert "group" in grouped.dims
    assert (grouped.group == [1, 2]).all()
    assert grouped._term.size == 10

    # now asymetric groups which result in different nterms
    groups = xr.DataArray([1] * 12 + [2] * 8, coords=v.coords)
    grouped = v.to_linexpr().group_terms(groups)
    assert "group" in grouped.dims
    # first group must be full with vars
    assert (grouped.sel(group=1) > 0).all()
    # the last 4 entries of the second group must be empty, i.e. -1
    assert (grouped.sel(group=2).isel(_term=slice(None, -4)).vars >= 0).all()
    assert (grouped.sel(group=2).isel(_term=slice(-4, None)).vars == -1).all()
    assert grouped._term.size == 12


def test_group_terms_variable():
    groups = xr.DataArray([1] * 10 + [2] * 10, coords=v.coords)
    grouped = v.group_terms(groups)
    assert "group" in grouped.dims
    assert (grouped.group == [1, 2]).all()
    assert grouped._term.size == 10
