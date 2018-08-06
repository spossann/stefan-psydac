# coding: utf-8
# Copyright 2018 Yaman Güçlü

from mpi4py import MPI
import numpy as np
import pytest

from spl.core.bsplines import make_knots
from spl.fem.basic     import FemField
from spl.fem.splines   import SplineSpace
from spl.fem.tensor    import TensorFemSpace

from spl.fem.tests.utilities              import horner, random_grid
from spl.fem.tests.splines_error_bounds   import spline_1d_error_bound
from spl.fem.tests.analytical_profiles_1d import (AnalyticalProfile1D_Cos,
                                                  AnalyticalProfile1D_Poly)

#===============================================================================
@pytest.mark.serial
@pytest.mark.parametrize( "ncells", [1,5,10,23] )
@pytest.mark.parametrize( "degree", range(1,11) )

def test_SplineInterpolation1D_exact( ncells, degree ):

    domain   = [-1.0, 1.0]
    periodic = False

    poly_coeffs = np.random.random_sample( degree+1 ) # 0 <= c < 1
    poly_coeffs = 1.0 - poly_coeffs                   # 0 < c <= 1
    f = lambda x : horner( x, *poly_coeffs )

    grid  = random_grid( domain, ncells, 0.5 )
    space = SplineSpace( degree=degree, grid=grid, periodic=periodic )
    field = FemField( space, 'f' )

    xg = space.greville
    ug = f( xg )

    space.compute_interpolant( ug, field )

    xt  = np.linspace( *domain, num=100 )
    err = np.array( [field( x ) - f( x ) for x in xt] )

    max_norm_err = np.max( abs( err ) )
    assert max_norm_err < 2.0e-14

#===============================================================================
def args_SplineInterpolation1D_cosine():
    for ncells in [5,10,23]:
        for periodic in [True, False]:
            pmax = min(ncells,9) if periodic else 9
            for degree in range(1,pmax+1):
                yield (ncells, degree, periodic)

@pytest.mark.serial
@pytest.mark.parametrize( "ncells,degree,periodic",
    args_SplineInterpolation1D_cosine() )

def test_SplineInterpolation1D_cosine( ncells, degree, periodic ):

    f = AnalyticalProfile1D_Cos()

    grid  = random_grid( f.domain, ncells, 0.5 )
    space = SplineSpace( degree=degree, grid=grid, periodic=periodic )
    field = FemField( space, 'f' )

    xg = space.greville
    ug = f.eval( xg )

    space.compute_interpolant( ug, field )
    xt  = np.linspace( *f.domain, num=100 )
    err = np.array( [field( x ) - f.eval( x ) for x in xt] )

    max_norm_err = np.max( abs( err ) )
    err_bound    = spline_1d_error_bound( f, np.diff( grid ).max(), degree )

    assert max_norm_err < err_bound

#===================================================================================
# TODO: move function to TensorFemSpace method
# TODO: generalize to any number of dimensions
#---------------------------------------------
def integral( V, f ):
    """
    Compute integral over domain of $f(x1,x2)$ using Gaussian quadrature.

    Parameters
    ----------
    V : TensorFemSpace
        Finite element space that defines the quadrature rule.
        (normally the quadrature is exact for any element of this space).

    f : callable
        Scalar function of location $(x1,x2)$.

    Returns
    -------
    c : float
        Integral of $f$ over domain.

    """
    # Sizes
    [s1, s2] = V.vector_space.starts
    [e1, e2] = V.vector_space.ends
    [p1, p2] = V.vector_space.pads

    # Quadrature data
    [      nq1,       nq2] = [W.quad_order   for W in V.spaces]
    [ points_1,  points_2] = [W.quad_points  for W in V.spaces]
    [weights_1, weights_2] = [W.quad_weights for W in V.spaces]

    # Element range
    (sk1,sk2), (ek1,ek2) = V.local_domain

    c = 0.0
    for k1 in range(sk1, ek1+1):
        for k2 in range(sk2, ek2+1):

            x1 =  points_1[k1,:]
            w1 = weights_1[k1,:]

            x2 =  points_2[k2,:]
            w2 = weights_2[k2,:]

            for q1 in range( nq1 ):
                for q2 in range( nq2 ):
                    c += f( x1[q1], x2[q2] ) * w1[q1] * w2[q2]

    # All reduce (MPI_SUM)
    # TODO: verify that it is OK to access private attribute
    mpi_comm = V.vector_space.cart._comm
    c = mpi_comm.allreduce( c )

    return c

#===============================================================================
@pytest.mark.xfail

@pytest.mark.parallel
@pytest.mark.parametrize( "nc1", [5,10,23] )
@pytest.mark.parametrize( "nc2", [5,10,23] )
@pytest.mark.parametrize( "deg1", range(1,5) )
@pytest.mark.parametrize( "deg2", range(1,5) )

def test_SplineInterpolation2D_parallel_exact( nc1, nc2, deg1, deg2 ):

    domain1   = [-1.0, 0.8]
    periodic1 = False

    domain2   = [-0.9, 1.0]
    periodic2 = False

    degree = min( deg1, deg2 )

    poly_coeffs = np.random.random_sample( degree+1 ) # 0 <= c < 1
    poly_coeffs = 1.0 - poly_coeffs                   # 0 < c <= 1
    f = lambda x1,x2 : horner( x1-0.5*x2, *poly_coeffs )

    # Along x1
    grid1  = random_grid( domain1, nc1, 0.0 )
    space1 = SplineSpace( degree=deg1, grid=grid1, periodic=periodic1 )

    # Along x2
    grid2  = random_grid( domain2, nc2, 0.0 )
    space2 = SplineSpace( degree=deg2, grid=grid2, periodic=periodic2 )

    # Tensor-product 2D spline space, distributed, and field
    tensor_space = TensorFemSpace( space1, space2, comm=MPI.COMM_WORLD )
    tensor_field = FemField( tensor_space, 'T' )

    # Coordinates of Greville points (global)
    x1g = space1.greville
    x2g = space2.greville

    # Interpolation data on Greville points (distributed)
    V     = tensor_space.vector_space
    ug    = V.zeros()
    s1,s2 = V.starts
    e1,e2 = V.ends
    for i1 in range( s1, e1+1 ):
        for i2 in range( s2, e2+1 ):
            ug[i1,i2] = f( x1g[i1], x2g[i2] )

    # Compute 2D spline interpolant
    tensor_space.compute_interpolant( ug, tensor_field )

    # Prepare FEM usage of splines (quadrature, etc.)
    for space in tensor_space.spaces: space.init_fem()

    # Compute L2 norm of error
    integrand = lambda *x: (tensor_field(*x) - f(*x))**2
    l2_error  = np.sqrt( integral( tensor_space, integrand ) )
    print( 'l2_error = {:.2e}'.format( l2_error ) )

    # Verify that error is only caused by finite precision arithmetic
    assert l2_error < 1.0e-14
