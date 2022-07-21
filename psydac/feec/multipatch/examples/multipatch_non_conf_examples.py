import os
from mpi4py import MPI

import numpy as np
import matplotlib.pyplot as plt
from collections import OrderedDict
from sympde.topology     import Derham

from psydac.feec.multipatch.api                         import discretize
from psydac.api.settings                                import PSYDAC_BACKENDS
from psydac.feec.multipatch.fem_linear_operators        import IdLinearOperator
from psydac.feec.multipatch.operators                   import HodgeOperator
from psydac.feec.multipatch.multipatch_domain_utilities import build_multipatch_domain
from psydac.feec.multipatch.plotting_utilities          import plot_field
from psydac.feec.multipatch.utilities                   import time_count, get_run_dir, get_plot_dir, get_mat_dir, get_sol_dir, diag_fn
from psydac.feec.multipatch.utils_conga_2d              import write_diags_to_file

from sympde.topology      import Square    
from sympde.topology      import IdentityMapping, PolarMapping
from psydac.fem.vector import ProductFemSpace

from scipy.sparse.linalg import spilu, lgmres
from scipy.sparse.linalg import LinearOperator, eigsh, minres
from scipy.sparse          import csr_matrix
from scipy.linalg        import norm

from psydac.linalg.utilities import array_to_stencil
from psydac.fem.basic        import FemField

from psydac.feec.multipatch.examples.non_conf_domains_examples import create_square_domain, construct_V1_conforming_projection

from psydac.api.postprocessing import OutputManager, PostProcessManager

def hcurl_solve_eigen_pbm_multipatch_nc(ncells=[[2,2], [2,2]], degree=[3,3], domain=[[0, np.pi],[0, np.pi]], domain_name='refined_square', backend_language='pyccel-gcc', mu=1, nu=0, gamma_h=0,
                          generalized_pbm=False, sigma=None, ref_sigmas=[], nb_eigs_solve=8, nb_eigs_plot=5, skip_eigs_threshold=1e-7,
                          plot_dir=None, hide_plots=True, m_load_dir="",):

    diags = {}
    
    if sigma is None:
        raise ValueError('please specify a value for sigma')

    print('---------------------------------------------------------------------------------------------------------')
    print('Starting hcurl_solve_eigen_pbm function with: ')
    print(' ncells = {}'.format(ncells))
    print(' degree = {}'.format(degree))
    print(' domain_name = {}'.format(domain_name))
    print(' backend_language = {}'.format(backend_language))
    print('---------------------------------------------------------------------------------------------------------')

    print('building symbolic and discrete domain...')

    int_x, int_y = domain
    
    if domain_name == 'refined_square' or domain_name =='square_L_shape':
        domain = create_square_domain(ncells, int_x, int_y, mapping='identity')
    
    elif domain_name == 'curved_L_shape':
        domain = create_square_domain(ncells, int_x, int_y, mapping='polar')
    
    ncells_h = {patch.name: [ncells[int(patch.name[2])][int(patch.name[4])], ncells[int(patch.name[2])][int(patch.name[4])]] for patch in domain.interior}


    mappings = OrderedDict([(P.logical_domain, P.mapping) for P in domain.interior])
    mappings_list = list(mappings.values())

    print('building symbolic and discrete derham sequences...')
    
    t_stamp = time_count()
    print(' .. derham sequence...')
    derham  = Derham(domain, ["H1", "Hcurl", "L2"])


    t_stamp = time_count(t_stamp)
    print(' .. discrete domain...')
    domain_h = discretize(domain, ncells=ncells_h)   # Vh space

    t_stamp = time_count(t_stamp)
    print(' .. discrete derham sequence...')
    derham_h = discretize(derham, domain_h, degree=degree, backend=PSYDAC_BACKENDS[backend_language])

    
    V0h = derham_h.V0
    V1h = derham_h.V1
    V2h = derham_h.V2    
    print('dim(V0h) = {}'.format(V0h.nbasis))
    print('dim(V1h) = {}'.format(V1h.nbasis))
    print('dim(V2h) = {}'.format(V2h.nbasis))
    diags['ndofs_V0'] = V0h.nbasis
    diags['ndofs_V1'] = V1h.nbasis
    diags['ndofs_V2'] = V2h.nbasis


    t_stamp = time_count(t_stamp)
    print('building the discrete operators:')
    #print('commuting projection operators...')
    #nquads = [4*(d + 1) for d in degree]
    #P0, P1, P2 = derham_h.projectors(nquads=nquads)

    I1 = IdLinearOperator(V1h)
    I1_m = I1.to_sparse_matrix()

    t_stamp = time_count(t_stamp)
    print('Hodge operators...')
    # multi-patch (broken) linear operators / matrices
    #H0 = HodgeOperator(V0h, domain_h, backend_language=backend_language, load_dir=m_load_dir, load_space_index=0)
    H1 = HodgeOperator(V1h, domain_h, backend_language=backend_language, load_dir=m_load_dir, load_space_index=1)
    H2 = HodgeOperator(V2h, domain_h, backend_language=backend_language, load_dir=m_load_dir, load_space_index=2)

    #H0_m  = H0.to_sparse_matrix()           # = mass matrix of V0
    #dH0_m = H0.get_dual_sparse_matrix()     # = inverse mass matrix of V0
    H1_m  = H1.to_sparse_matrix()           # = mass matrix of V1
    dH1_m = H1.get_dual_sparse_matrix()     # = inverse mass matrix of V1
    H2_m  = H2.to_sparse_matrix()           # = mass matrix of V2

    t_stamp = time_count(t_stamp)
    print('conforming projection operators...')
    # conforming Projections (should take into account the boundary conditions of the continuous deRham sequence)

    
    
    cP1_m = construct_V1_conforming_projection(V1h, domain_h, hom_bc=True)
    #nbasis = 7
    #nbasis_d = 6

    #k_minus = range(84,126) 
    #k_plus = range(126,168)

    #k_minus_interface = k_minus[-nbasis_d:]
    #k_plus_interface = k_plus[0:nbasis_d]

    #cP1 = np.eye(168)
    #cP1[k_minus_interface, k_minus_interface] *= 1/2
    #cP1[k_plus_interface, k_plus_interface] *= 1/2

    #cP1[k_plus_interface, k_minus_interface] = np.ones(6)*1/2
    #cP1[k_minus_interface, k_plus_interface] = np.ones(6)*1/2
    #cP1_m = csr_matrix(cP1)
    
    
    
    #np.set_printoptions(linewidth=100000, precision=2, threshold=100000, suppress=True)
    np.savetxt('cP1.out', cP1_m.toarray(), delimiter=',')     
    #return None#
    #f = open('cP1.txt', 'w')
    #print(cP1_m.toarray(), file=f)
    cP0_m = None

    t_stamp = time_count(t_stamp)
    print('broken differential operators...')
    bD0, bD1 = derham_h.broken_derivatives_as_operators
    #bD0_m = bD0.to_sparse_matrix()
    bD1_m = bD1.to_sparse_matrix()

    t_stamp = time_count(t_stamp)
    print('converting some matrices to csr format...')

    H1_m = H1_m.tocsr()
    H2_m = H2_m.tocsr()
    cP1_m = cP1_m.tocsr()
    bD1_m = bD1_m.tocsr()    

    if not os.path.exists(plot_dir):
        os.makedirs(plot_dir)

    print('computing the full operator matrix...')
    A_m = np.zeros_like(H1_m) 

    # Conga (projection-based) stiffness matrices
    if mu != 0:
        # curl curl:
        t_stamp = time_count(t_stamp)
        print('mu = {}'.format(mu))
        print('curl-curl stiffness matrix...')
        
        pre_CC_m = bD1_m.transpose() @ H2_m @ bD1_m
        CC_m = cP1_m.transpose() @ pre_CC_m @ cP1_m  # Conga stiffness matrix
        A_m += mu * CC_m 

    # jump stabilization in V1h:
    if gamma_h != 0 or generalized_pbm:
        t_stamp = time_count(t_stamp)
        print('jump stabilization matrix...')
        jump_stab_m = I1_m - cP1_m
        JS_m = jump_stab_m.transpose() @ H1_m @ jump_stab_m
        
    if generalized_pbm:
        print('adding jump stabilization to RHS of generalized eigenproblem...')
        B_m = cP1_m.transpose() @ H1_m @ cP1_m + JS_m
    else:
        B_m = H1_m
    

    t_stamp = time_count(t_stamp)
    print('solving matrix eigenproblem...')
    all_eigenvalues, all_eigenvectors_transp = get_eigenvalues(nb_eigs_solve, sigma, A_m, B_m)
    t_stamp = time_count(t_stamp)
    print('sorting out eigenvalues...')
    zero_eigenvalues = []
    if skip_eigs_threshold is not None:
        eigenvalues = []
        eigenvectors = []
        for val, vect in zip(all_eigenvalues, all_eigenvectors_transp.T):
            if abs(val) < skip_eigs_threshold: 
                zero_eigenvalues.append(val)
                # we skip the eigenvector
            else:
                eigenvalues.append(val)
                eigenvectors.append(vect)
    else:
        eigenvalues = all_eigenvalues
        eigenvectors = all_eigenvectors_transp.T

    for k, val in enumerate(eigenvalues):
        diags['eigenvalue_{}'.format(k)] = val #eigenvalues[k]
    
    for k, val in enumerate(zero_eigenvalues):
        diags['skipped eigenvalue_{}'.format(k)] = val

    t_stamp = time_count(t_stamp)
    print('plotting the eigenmodes...')     
    cb_min=-5 
    cb_max=5

    OM = OutputManager('spaces.yml', 'fields.h5')

    i = 0
    OM.add_spaces(V1=V1h)

    emode_i = np.real(eigenvectors[i])
    norm_emode_i = np.dot(emode_i,H1_m.dot(emode_i))
    eh_c = emode_i/norm_emode_i 
    stencil_coeffs = array_to_stencil(eh_c, V1h.vector_space)
    vh = FemField(V1h, coeffs=stencil_coeffs)
    OM.set_static()
    OM.export_fields(e_0 = vh)
    OM.export_space_info()
    
    PM = PostProcessManager(domain=domain, space_file='spaces.yml', fields_file='fields.h5' )
    
    
    PM.export_to_vtk("e_0",grid=None, npts_per_cell=[4]*2,snapshots='none',fields=('e_0') )
    
    
    nb_eigs = len(eigenvalues)
    for i in range(min(nb_eigs_plot, nb_eigs)):

        print('looking at emode i = {}... '.format(i))
        lambda_i  = eigenvalues[i]
        # emode_i = np.real(eigenvectors[:,i])
        emode_i = np.real(eigenvectors[i])
        norm_emode_i = np.dot(emode_i,H1_m.dot(emode_i))
        print('norm of computed eigenmode: ', norm_emode_i)
        # plot the broken eigenmode:
        eh_c = emode_i/norm_emode_i  # numpy coeffs of the normalized eigenmode
        params_str = 'gamma_h={}_gen={}'.format(gamma_h, generalized_pbm)
        #params_str = 'ndof={}'.format(V1h.nbasis)
        plot_field(numpy_coeffs=eh_c, Vh=V1h, space_kind='hcurl', domain=domain, title='e_{}, lambda_{}={}'.format(i,i,lambda_i),
                    filename=plot_dir+'/'+params_str+'_e_{}.png'.format(i), hide_plot=hide_plots)

        plot_field(numpy_coeffs=eh_c, Vh=V1h, space_kind='hcurl', domain=domain, title='e_{}, lambda_{}={}'.format(i,i,lambda_i), 
                    filename=plot_dir+'/'+params_str+'_e_{}_comps.png'.format(i),
                    plot_type='components', hide_plot=hide_plots)

        # also plot the projected eigenmode:
        Peh_c = cP1_m.dot(eh_c)
        plot_field(numpy_coeffs=Peh_c, Vh=V1h, space_kind='hcurl', domain=domain, title='P e_{}, lambda_{}={}'.format(i,i,lambda_i),
                    filename=plot_dir+'/'+params_str+'_Pe_{}.png'.format(i), hide_plot=hide_plots)
        # same, as vector field:
        plot_field(numpy_coeffs=Peh_c, Vh=V1h, space_kind='hcurl', domain=domain, title='P e_{}, lambda_{}={}'.format(i,i,lambda_i), 
                    filename=plot_dir+'/'+params_str+'_Pe_{}_vf.png'.format(i),
                    plot_type='vector_field', hide_plot=hide_plots)


        plot_checks = False
        if plot_checks:
            # check: plot jump
            plot_field(numpy_coeffs=eh_c-Peh_c, Vh=V1h, space_kind='hcurl', domain=domain, title='(I-P) e_{}, lambda_{}={}'.format(i,i,lambda_i),
                        filename=plot_dir+'/'+params_str+'_Jump_e_{}.png'.format(i), hide_plot=hide_plots)

            # check: curl e_i
            Ceh_c = bD1_m @ cP1_m.dot(eh_c)
            plot_field(numpy_coeffs=Ceh_c, Vh=V2h, space_kind='l2', domain=domain, title='C e_{}, lambda_{}={}'.format(i,i,lambda_i),
                        filename=plot_dir+'/'+params_str+'_Ce_{}.png'.format(i), hide_plot=hide_plots)

            # check: curl curl e_i
            CCeh_c = dH1_m @ cP1_m.transpose() @ bD1_m.transpose() @ H2_m @ Ceh_c
            plot_field(numpy_coeffs=CCeh_c, Vh=V1h, space_kind='hcurl', domain=domain, title='CC e_{}'.format(i),
                        filename=plot_dir+'/'+params_str+'_CCe_{}.png'.format(i), hide_plot=hide_plots)

            # check: filtered lambda_i * e_i (should be = curl curl e_i)
            fl_eh_c = lambda_i * dH1_m @ cP1_m.transpose() @ H1_m @ Peh_c
            plot_field(numpy_coeffs=fl_eh_c, Vh=V1h, space_kind='hcurl', domain=domain, title='filtered lambda_i * e_{}'.format(i),
                        filename=plot_dir+'/'+params_str+'_fl_e_{}.png'.format(i), hide_plot=hide_plots)
    t_stamp = time_count(t_stamp)

    if ref_sigmas is not None:
        errors = []
        n_errs = min(len(ref_sigmas), len(eigenvalues))
        for k in range(n_errs):
            diags['error_{}'.format(k)] = abs(eigenvalues[k]-ref_sigmas[k])

    return diags


def get_eigenvalues(nb_eigs, sigma, A_m, M_m):
    print('-----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  -----  ----- ')
    print('computing {0} eigenvalues (and eigenvectors) close to sigma={1} with scipy.sparse.eigsh...'.format(nb_eigs, sigma) )
    mode = 'normal'
    which = 'LM'
    # from eigsh docstring:
    #   ncv = number of Lanczos vectors generated ncv must be greater than k and smaller than n;
    #   it is recommended that ncv > 2*k. Default: min(n, max(2*k + 1, 20))
    ncv = 4*nb_eigs
    print('A_m.shape = ', A_m.shape)
    try_lgmres = True
    max_shape_splu = 24000   # OK for nc=20, deg=6 on pretzel_f
    if A_m.shape[0] < max_shape_splu:
        print('(via sparse LU decomposition)')
        OPinv = None
        tol_eigsh = 0
    else:

        OP_m = A_m - sigma*M_m
        tol_eigsh = 1e-7
        if try_lgmres:
            print('(via SPILU-preconditioned LGMRES iterative solver for A_m - sigma*M1_m)')
            OP_spilu = spilu(OP_m, fill_factor=15, drop_tol=5e-5)
            preconditioner = LinearOperator(OP_m.shape, lambda x: OP_spilu.solve(x) )
            tol = tol_eigsh
            OPinv = LinearOperator(
                matvec=lambda v: lgmres(OP_m, v, x0=None, tol=tol, atol=tol, M=preconditioner,
                                    callback=lambda x: print('cg -- residual = ', norm(OP_m.dot(x)-v))
                                    )[0],
                shape=M_m.shape,
                dtype=M_m.dtype
            )

        else:
            # from https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.eigsh.html:
            # the user can supply the matrix or operator OPinv, which gives x = OPinv @ b = [A - sigma * M]^-1 @ b.
            # > here, minres: MINimum RESidual iteration to solve Ax=b
            # suggested in https://github.com/scipy/scipy/issues/4170
            print('(with minres iterative solver for A_m - sigma*M1_m)')
            OPinv = LinearOperator(matvec=lambda v: minres(OP_m, v, tol=1e-10)[0], shape=M_m.shape, dtype=M_m.dtype)

    eigenvalues, eigenvectors = eigsh(A_m, k=nb_eigs, M=M_m, sigma=sigma, mode=mode, which=which, ncv=ncv, tol=tol_eigsh, OPinv=OPinv)

    print("done: eigenvalues found: " + repr(eigenvalues))
    return eigenvalues, eigenvectors