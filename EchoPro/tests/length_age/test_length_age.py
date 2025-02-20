import pytest

import os
import pandas as pd
import numpy as np
import EchoPro
from EchoPro.computation import SemiVariogram as SV


def test_transect_based_length_age(config_base_path, matlab_output_base_path):

    # TODO: formalize this test

    # change working directory so no initialization files need to be modified
    # TODO: this may not be necessary in the future
    os.chdir(config_base_path)

    # initialize Survey object
    survey_2019 = EchoPro.Survey(init_file_path='../config_files/initialization_config.yml',
                                 survey_year_file_path='../config_files/survey_year_2019_config.yml',
                                 source=3,
                                 exclude_age1=True)

    # load all data
    survey_2019.load_survey_data()

    # compute all transect variables
    survey_2019.compute_transect_results()

    # compute abundance and biomass for each length and age bin
    survey_2019.compute_length_age_variables(data="transect")

    # set variables to improve readability
    abundance_df = survey_2019.bio_calc.transect_bin_abundance_df
    male_abundance_df = survey_2019.bio_calc.transect_bin_abundance_male_df
    female_abundance_df = survey_2019.bio_calc.transect_bin_abundance_female_df
    biomass_df = survey_2019.bio_calc.transect_bin_biomass_df
    male_biomass_df = survey_2019.bio_calc.transect_bin_biomass_male_df
    female_biomass_df = survey_2019.bio_calc.transect_bin_biomass_female_df

    # obtain file_path pointing to the known abundance data
    file_path_abundance = matlab_output_base_path / "un-kriged_len_age_abundance_table.xlsx"
    sheet_name = "Sheet3"
    sheet_name_male = "Sheet1"
    sheet_name_female = "Sheet2"

    # gather known solution data produced by the Matlab version of EchoPro
    df_known = pd.read_excel(file_path_abundance, index_col=0, sheet_name=sheet_name, skiprows=[0, 42, 43, 44, 45, 46], usecols="A:X")
    male_df_known = pd.read_excel(file_path_abundance, index_col=0, sheet_name=sheet_name_male,
                                  skiprows=[0, 42, 43, 44, 45, 46], usecols="A:X")
    female_df_known = pd.read_excel(file_path_abundance, index_col=0, sheet_name=sheet_name_female,
                                    skiprows=[0, 42, 43, 44, 45, 46], usecols="A:X")

    # compare known and produced values for abundance
    assert np.all(np.isclose(df_known.to_numpy(), abundance_df.to_numpy()))

    assert np.all(np.isclose(male_df_known.to_numpy(), male_abundance_df.to_numpy()))

    assert np.all(np.isclose(female_df_known.to_numpy(), female_abundance_df.to_numpy()))

    # obtain file_path pointing to the known biomass data
    file_path_biomass = matlab_output_base_path / "un-kriged_len_age_biomass_table.xlsx"

    # gather known solution data produced by the Matlab version of EchoPro
    df_known = pd.read_excel(file_path_biomass, index_col=0, sheet_name=sheet_name,
                             skiprows=[0, 42, 43, 44, 45, 46], usecols="A:W")
    male_df_known = pd.read_excel(file_path_biomass, index_col=0, sheet_name=sheet_name_male,
                                  skiprows=[0, 42, 43, 44, 45, 46], usecols="A:W")
    female_df_known = pd.read_excel(file_path_biomass, index_col=0, sheet_name=sheet_name_female,
                                    skiprows=[0, 42, 43, 44, 45, 46], usecols="A:W")

    # compare known and produced values for biomass
    assert np.all(np.isclose(1e9 * df_known.to_numpy(), biomass_df.to_numpy()))

    assert np.all(np.isclose(1e9 * male_df_known.to_numpy(), male_biomass_df.to_numpy()))

    assert np.all(np.isclose(1e9 * female_df_known.to_numpy(), female_biomass_df.to_numpy()))


def test_kriging_based_length_age(config_base_path, matlab_output_base_path):
    # TODO: formalize this test

    # change working directory so no initialization files need to be modified
    # TODO: this may not be necessary in the future
    os.chdir(config_base_path)

    # initialize Survey object
    survey_2019 = EchoPro.Survey(init_file_path='../config_files/initialization_config.yml',
                                 survey_year_file_path='../config_files/survey_year_2019_config.yml',
                                 source=3,
                                 exclude_age1=True)

    # load all data
    survey_2019.load_survey_data()

    # compute all transect variables
    survey_2019.compute_transect_results()

    # initialize Kriging mesh object and apply appropriate coordinate transformations
    krig_mesh = survey_2019.get_kriging_mesh()
    krig_mesh.apply_coordinate_transformation(coord_type='transect')
    krig_mesh.apply_coordinate_transformation(coord_type='mesh')

    kriging_params = dict(
        # kriging parameters
        k_max=10,
        k_min=3,
        R=0.0226287,
        ratio=0.001,

        # parameters for semi-variogram model
        s_v_params={'nugget': 0.0, 'sill': 0.95279, 'ls': 0.0075429,
                    'exp_pow': 1.5, 'ls_hole_eff': 0.0},

        # grab appropriate semi-variogram model
        s_v_model=SV.generalized_exp_bessel
    )

    # initialize kriging routine
    krig = survey_2019.get_kriging(kriging_params)

    # run Kriging routine
    krig.run_biomass_kriging(krig_mesh)

    # compute additional variables at each Kriging mesh point
    krig.compute_kriging_variables()

    # compute abundance and biomass for each length and age bin
    survey_2019.compute_length_age_variables(data="kriging")

    # set variables to improve readability
    abundance_df = survey_2019.bio_calc.kriging_bin_abundance_df
    male_abundance_df = survey_2019.bio_calc.kriging_bin_abundance_male_df
    female_abundance_df = survey_2019.bio_calc.kriging_bin_abundance_female_df
    biomass_df = survey_2019.bio_calc.kriging_bin_biomass_df
    male_biomass_df = survey_2019.bio_calc.kriging_bin_biomass_male_df
    female_biomass_df = survey_2019.bio_calc.kriging_bin_biomass_female_df

    # obtain file_path pointing to the known abundance data
    file_path_abundance = matlab_output_base_path / "kriged_len_age_abundance_table.xlsx"
    sheet_name = "Sheet3"
    sheet_name_male = "Sheet1"
    sheet_name_female = "Sheet2"

    # gather known solution data produced by the Matlab version of EchoPro
    df_known = pd.read_excel(file_path_abundance, index_col=0, sheet_name=sheet_name, skiprows=[0, 42, 43, 44, 45, 46],
                             usecols="A:X")
    male_df_known = pd.read_excel(file_path_abundance, index_col=0, sheet_name=sheet_name_male,
                                  skiprows=[0, 42, 43, 44, 45, 46], usecols="A:X")
    female_df_known = pd.read_excel(file_path_abundance, index_col=0, sheet_name=sheet_name_female,
                                    skiprows=[0, 42, 43, 44, 45, 46], usecols="A:X")

    # compare known and produced values for abundance
    assert np.all(np.isclose(df_known.to_numpy(), abundance_df.to_numpy()))

    assert np.all(np.isclose(male_df_known.to_numpy(), male_abundance_df.to_numpy()))

    assert np.all(np.isclose(female_df_known.to_numpy(), female_abundance_df.to_numpy()))

    # obtain file_path pointing to the known biomass data
    file_path_biomass = matlab_output_base_path / "kriged_len_age_biomass_table.xlsx"

    # gather known solution data produced by the Matlab version of EchoPro
    df_known = pd.read_excel(file_path_biomass, index_col=0, sheet_name=sheet_name,
                             skiprows=[0, 42, 43, 44, 45, 46], usecols="A:W")
    male_df_known = pd.read_excel(file_path_biomass, index_col=0, sheet_name=sheet_name_male,
                                  skiprows=[0, 42, 43, 44, 45, 46], usecols="A:W")
    female_df_known = pd.read_excel(file_path_biomass, index_col=0, sheet_name=sheet_name_female,
                                    skiprows=[0, 42, 43, 44, 45, 46], usecols="A:W")

    # compare known and produced values for biomass
    assert np.all(np.isclose(1e9 * df_known.to_numpy(), biomass_df.to_numpy()[:, :-1]))

    assert np.all(np.isclose(1e9 * male_df_known.to_numpy(), male_biomass_df.to_numpy()[:, :-1]))

    assert np.all(np.isclose(1e9 * female_df_known.to_numpy(), female_biomass_df.to_numpy()[:, :-1]))
