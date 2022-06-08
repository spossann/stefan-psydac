import os
import numpy as np
from psydac.feec.multipatch.examples.h1_source_pbms_conga_2d import solve_h1_source_pbm
from psydac.feec.multipatch.utilities                   import time_count, FEM_sol_fn, get_run_dir, get_plot_dir, get_mat_dir, get_sol_dir, diag_fn
from psydac.feec.multipatch.utils_conga_2d              import write_diags_to_file

t_stamp_full = time_count()

# ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- 
#
# test-case and numerical parameters:

homogeneous = True # False # 

# nc_s = [2,4,8,16]
nc_s = [20]
deg_s = [2,3,4,5]

# nc = 16 
# deg = 4

if homogeneous:
    case_dir = 'poisson_hom'
    source_type = 'manu_poisson_elliptic'
    domain_name = 'pretzel_f'
    
    # domain_name = 'curved_L_shape'
else:
    case_dir = 'poisson_inhom'
    source_type = 'manu_poisson_sincos' # 'manu_poisson_2'
    domain_name = 'pretzel_f'
    # domain_name = 'curved_L_shape'
    # raise NotImplementedError

source_proj = 'P_L2'
# source_proj='P_geom' # geom proj (interpolation) of source: quicker but not standard

filter_source = True # False # 
project_sol = False # True # 
gamma_h = 10

# ref solution (if no exact solution)
ref_nc = 2
ref_deg = 2

#
# ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- 

common_diag_filename = './'+case_dir+'_diags.txt'

for nc in nc_s:
    for deg in deg_s:

        params = {
            'domain_name': domain_name,
            'nc': nc,
            'deg': deg,
            'homogeneous': homogeneous,
            'source_type': source_type,
            'source_proj': source_proj, 
            'project_sol': project_sol,
            'filter_source': filter_source,
            'ref_nc': ref_nc,
            'ref_deg': ref_deg,
        }

        # backend_language = 'numba'
        backend_language='pyccel-gcc'

        run_dir = get_run_dir(domain_name, nc, deg, source_type=source_type)
        plot_dir = get_plot_dir(case_dir, run_dir)
        diag_filename = plot_dir+'/'+diag_fn(source_type=source_type, source_proj=source_proj)

        # to save and load matrices
        m_load_dir = get_mat_dir(domain_name, nc, deg)
        # to save the FEM sol
        sol_dir = get_sol_dir(case_dir, domain_name, nc, deg)
        sol_filename = sol_dir+'/'+FEM_sol_fn(source_type=source_type, source_proj=source_proj)
        if not os.path.exists(sol_dir):
            os.makedirs(sol_dir)
        # to load the ref FEM sol
        sol_ref_dir = get_sol_dir(case_dir, domain_name, ref_nc, ref_deg)
        sol_ref_filename = sol_ref_dir+'/'+FEM_sol_fn(source_type=source_type, source_proj=source_proj)

        print('\n --- --- --- --- --- --- --- --- --- --- --- --- --- --- \n')
        print(' Calling solve_h1_source_pbm() with params = {}'.format(params))
        print('\n --- --- --- --- --- --- --- --- --- --- --- --- --- --- \n')

        # ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- 
        # calling solver for:
        # 
        # find u in H1, s.t.
        #       A u = f             on \Omega
        #         u = u_bc          on \partial \Omega
        # with
        #       A u := eta * u  -  mu * div grad u

        diags = solve_h1_source_pbm(
            nc=nc, deg=deg,
            eta=0,
            mu=1,
            domain_name=domain_name,
            source_type=source_type,
            source_proj=source_proj,   
            backend_language=backend_language,
            plot_source=True,
            project_sol=project_sol,
            plot_dir=plot_dir,
            hide_plots=True,
            m_load_dir=m_load_dir,
            sol_filename=sol_filename,
            sol_ref_filename=sol_ref_filename,
            ref_nc=ref_nc,
            ref_deg=ref_deg,    
        )

        #
        # ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- 

        write_diags_to_file(diags, script_filename=__file__, diag_filename=diag_filename, params=params)
        write_diags_to_file(diags, script_filename=__file__, diag_filename=common_diag_filename, params=params)

time_count(t_stamp_full, msg='full program')