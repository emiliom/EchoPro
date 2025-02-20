from typing import Callable, Tuple, TypedDict

import geopandas as gpd
import numpy as np
import pandas as pd

from ..data_loader import KrigingMesh
from .kriging_variables import ComputeKrigingVariables
from .numba_functions import nb_dis_mat, nb_subtract_outer

# define the Kriging parameter input types
krig_type_dict = {
    "k_max": int,
    "k_min": int,
    "R": float,
    "ratio": float,
    "s_v_params": dict,
    "s_v_model": Callable,
}
krig_param_type = TypedDict("krig_param_type", krig_type_dict)


class Kriging:
    """
    This class constructs all data necessary
    for Kriging and performs Kriging

    Parameters
    ----------
    survey : Survey
        An initialized Survey object. Note that any change to
        ``self.survey`` will also change this object.
    k_max: int
        The maximum number of data points within the search radius
    k_min: int
        The minimum number of data points within the search radius
    R: float
        Search radius for Kriging
    ratio: float
        Acceptable ratio for the singular values divided by the largest
        singular value.
    s_v_params: dict
        Dictionary specifying the parameter values for the semi-variogram model.
    s_v_model: Callable
        a Semi-variogram model from the ``SemiVariogram`` class
    """

    def __init__(
        self,
        survey=None,
        k_max: int = None,
        k_min: int = None,
        R: float = None,
        ratio: float = None,
        s_v_params: dict = None,
        s_v_model: Callable = None,
    ):

        self.survey = survey
        self.krig_bio_calc = None

        # Kriging parameters
        self.k_max = k_max
        self.k_min = k_min
        self.R = R
        self.ratio = ratio

        # parameters for semi-variogram model
        self.s_v_params = s_v_params

        # grab appropriate semi-variogram model
        self.s_v_model = s_v_model

    def _compute_k_smallest_distances(
        self,
        x_mesh: np.ndarray,
        x_data: np.ndarray,
        y_mesh: np.ndarray,
        y_data: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes the distance between the data
        and the mesh points. Using the distance, it then
        selects the kmax smallest values amongst the
        columns.

        Parameters
        ----------
        x_mesh : np.ndarray
            1D array denoting the x coordinates of the mesh
        x_data : np.ndarray
            1D array denoting the x coordinates of the data
        y_mesh : np.ndarray
            1D array denoting the y coordinates of the mesh
        y_data : np.ndarray
            1D array denoting the y coordinates of the data

        Returns
        -------
        dis : np.ndarray
            2D array representing the distance between each
            mesh point and each transect point
        dis_kmax_ind : np.ndarray
            A 2D array index array representing the kmax
            closest transect points to each mesh point.
        """

        # compute the distance between the mesh points and transect points
        x_diff = nb_subtract_outer(x_mesh, x_data)
        y_diff = nb_subtract_outer(y_mesh, y_data)
        dis = nb_dis_mat(x_diff, y_diff)

        # sort dis up to the kmax smallest elements in each row
        dis_sort_ind = np.argpartition(dis, self.k_max, axis=1)

        # select only the kmax smallest elements in each row
        dis_kmax_ind = dis_sort_ind[:, : self.k_max]

        return dis, dis_kmax_ind

    def _get_indices_and_weight(
        self, dis_kmax_ind: np.ndarray, row: int, dis: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        """
        Obtains the indices of ``dis`` that are in ``R``, outside ``R``, and
        the ``k_max`` smallest values. Additionally, obtains the weight
        for points outside the transect region.


        Parameters
        ----------
        dis_kmax_ind : np.ndarray
            The indices of ``dis`` that represent the ``k_max`` smallest
            values
        row : int
            Row index of ``dis_kmax_ind`` being considered
        dis : np.ndarray
            2D numpy array representing the distance between each
            mesh point and each transect point

        Returns
        -------
        R_ind : np.ndarray
            Indices of ``dis`` that are in ``R``
        R_ind_not : np.ndarray
            Indices of ``dis`` that are outside ``R``
        sel_ind : np.ndarray
            Indices of ``dis`` representing the ``k_max`` smallest values
        M2_weight : float
            The weight for points outside the transect region.
        """

        # weight for points outside of transect region
        M2_weight = 1.0

        # get indices of dis
        sel_ind = dis_kmax_ind[row, :]

        # get all indices within R
        R_ind = np.argwhere(dis[row, sel_ind] <= self.R).flatten()

        if len(R_ind) < self.k_min:

            # get the k_min smallest distance values' indices
            R_ind = np.argsort(dis[row, sel_ind]).flatten()[: self.k_min]

            # get the indices of sel_ind[R_ind] that are outside of R
            R_ind_not = np.argwhere(dis[row, sel_ind[R_ind]] > self.R).flatten()

            # TODO: should we change this to how Chu does it?
            # tapered function to handle extrapolation
            M2_weight = np.exp(-np.nanmean(dis[row, sel_ind[R_ind]]) / self.R)
        else:
            R_ind_not = []

        return R_ind, R_ind_not, sel_ind, M2_weight

    def _get_M2_K(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        dis: np.ndarray,
        row: int,
        dis_sel_ind: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """

        Parameters
        ----------
        x_data : np.ndarray
            1D array denoting the x coordinates of the data
        y_data : np.ndarray
            1D array denoting the y coordinates of the data
        dis : np.ndarray
            2D numpy array representing the distance between each
            mesh point and each transect point
        row : int
            Row index of ``dis_kmax_ind`` being considered
        dis_sel_ind : np.ndarray
            Indices of ``dis`` within the search radius

        Returns
        -------
        M2 : np.ndarray
            1D array representing the vector in Kriging
        K : np.ndarray
            2D array representing the matrix in Kriging
        """

        # calculate semi-variogram value
        M20 = self.s_v_model(dis[row, dis_sel_ind], **self.s_v_params)

        # TODO: Should we put in statements for Objective mapping and Universal Kriging w/ Linear drift?  # noqa
        M2 = np.concatenate([M20, np.array([1.0])])  # for Ordinary Kriging

        # select those data within the search radius
        x1 = x_data[dis_sel_ind]
        y1 = y_data[dis_sel_ind]

        # compute the distance between the points
        x1_diff = np.subtract.outer(x1, x1)
        y1_diff = np.subtract.outer(y1, y1)
        dis1 = np.sqrt(x1_diff * x1_diff + y1_diff * y1_diff)

        # calculate semi-variogram value
        K0 = self.s_v_model(dis1, **self.s_v_params)

        # TODO: Should we put in statements for Objective mapping and Universal Kriging w/ Linear drift?  # noqa
        # Add column and row of ones for Ordinary Kriging
        K = np.concatenate([K0, np.ones((len(x1), 1))], axis=1)
        K = np.concatenate([K, np.ones((1, len(x1) + 1))], axis=0)

        # do an inplace fill of diagonal
        np.fill_diagonal(K, 0.0)

        return M2, K

    def _compute_lambda_weights(self, M2: np.ndarray, K: np.ndarray) -> np.ndarray:
        """
        Computes the lambda weights of Kriging.

        Parameters
        ----------
        M2 : np.ndarray
            1D array representing the vector in Kriging
        K : np.ndarray
            2D array representing the matrix in Kriging

        Returns
        -------
        lamb : np.ndarray
            Lambda weights computed from Kriging
        """

        # compute SVD
        u, s, vh = np.linalg.svd(K, full_matrices=True)

        kindx = np.argwhere(np.abs(s / s[0]) > self.ratio).flatten()

        s_inv = 1.0 / s[kindx]

        k_inv = np.matmul(vh.T[:, kindx], np.diag(s_inv))
        k_inv = np.matmul(k_inv, u[:, kindx].T)

        lamb = np.dot(k_inv, M2)

        return lamb

    @staticmethod
    def _compute_kriging_vals(
        field_data: np.ndarray,
        M2: np.ndarray,
        lamb: np.ndarray,
        M2_weight: float,
        R_ind: np.ndarray,
        R_ind_not: np.ndarray,
        dis_sel_ind: np.ndarray,
    ) -> Tuple[float, float, float]:
        """
        Computes the Kriging mean, variance, and sample variance.

        Parameters
        ----------
        field_data : np.ndarray
            1D array denoting the field values at the (x ,y)
            coordinates of the data (e.g. biomass density).
        M2 : np.ndarray
            1D array representing the vector in Kriging
        lamb : np.ndarray
            Lambda weights of Kriging
        M2_weight : float
            The weight for points outside the transect region.
        R_ind : np.ndarray
            Indices of dis that are in R
        R_ind_not : np.ndarray
            Indices of dis that are outside R
        dis_sel_ind : np.ndarray
            Indices of dis within the search radius

        Returns
        -------
        field_var : float
            Kriging variance
        field_samplevar : float
            Kriging sample variance
        field_mean : float
            Kriged value mean
        """

        # obtain field values for indices within R
        if len(R_ind_not) > 0:
            field_vals = field_data[dis_sel_ind]
            field_vals[R_ind_not] = 0.0  # accounts for less than k_min points
        else:
            field_vals = field_data[dis_sel_ind]

        # calculate Kriging value and variance
        field_mean = np.nansum(lamb[: len(R_ind)] * field_vals) * M2_weight
        field_var = np.nansum(lamb * M2)

        # calculate Kriging sample variance
        if abs(field_mean) < np.finfo(float).eps:
            field_samplevar = np.nan
        else:
            # compute the statistical variance using field values
            stat_field_var = np.nanvar(field_vals, ddof=1)
            field_samplevar = np.sqrt(field_var * stat_field_var) / abs(field_mean)

        # TODO: Do we count the anomalies like Chu does?

        return field_var, field_samplevar, field_mean

    def run_kriging(
        self,
        x_mesh: np.ndarray,
        x_data: np.ndarray,
        y_mesh: np.ndarray,
        y_data: np.ndarray,
        field_data: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        A low-level interface that runs Kriging using the provided
        mesh and data.

        Parameters
        ----------
        x_mesh : np.ndarray
            1D array denoting the x coordinates of the mesh
        x_data : np.ndarray
            1D array denoting the x coordinates of the data
        y_mesh : np.ndarray
            1D array denoting the y coordinates of the mesh
        y_data : np.ndarray
            1D array denoting the y coordinates of the data
        field_data : np.ndarray
            1D array denoting the field values at the (x ,y)
            coordinates of the data (e.g. biomass density).

        Returns
        -------
        field_var_arr : np.ndarray
            1D array representing the Kriging variance for each mesh coordinate
        field_samplevar_arr : np.ndarray
            1D array representing the Kriging sample variance for each mesh coordinate
        field_mean_arr : np.ndarray
            1D array representing the Kriged mean value for each mesh coordinate

        Notes
        -----
        Currently, this routine only runs Ordinary Kriging.
        """

        dis, dis_kmax_ind = self._compute_k_smallest_distances(
            x_mesh, x_data, y_mesh, y_data
        )

        # initialize arrays that store calculated Kriging values
        field_var_arr = np.empty(dis_kmax_ind.shape[0])
        field_samplevar_arr = np.empty(dis_kmax_ind.shape[0])
        field_mean_arr = np.empty(dis_kmax_ind.shape[0])

        # TODO: This loop can be parallelized, if necessary
        # does Ordinary Kriging, follow Journel and Huijbregts, p. 307
        for row in range(dis_kmax_ind.shape[0]):

            R_ind, R_ind_not, sel_ind, M2_weight = self._get_indices_and_weight(
                dis_kmax_ind, row, dis
            )

            # indices of dis within the search radius
            dis_sel_ind = sel_ind[R_ind]

            M2, K = self._get_M2_K(x_data, y_data, dis, row, dis_sel_ind)

            lamb = self._compute_lambda_weights(M2, K)

            field_var, field_samplevar, field_mean = self._compute_kriging_vals(
                field_data, M2, lamb, M2_weight, R_ind, R_ind_not, dis_sel_ind
            )

            # store important calculated values
            field_var_arr[row] = field_var
            field_samplevar_arr[row] = field_samplevar
            field_mean_arr[row] = field_mean

        # zero-out all field mean values that are nan or negative # TODO: Is this necessary?
        neg_nan_ind = np.argwhere(
            (field_mean_arr < 0) | np.isnan(field_mean_arr)
        ).flatten()
        field_mean_arr[neg_nan_ind] = 0.0

        return field_var_arr, field_samplevar_arr, field_mean_arr

    def run_biomass_kriging(self, krig_mesh: KrigingMesh) -> None:
        """
        A high-level interface that sets up and runs
        Kriging using the areal biomass density.
        The results are then stored in the ``Survey``
        object as ``kriging_results_gdf``.

        Parameters
        ----------
        krig_mesh : KrigingMesh
            Object representing the Kriging mesh

        Notes
        -----
        To run this routine, one must first compute the areal biomass
        density using ``compute_transect_results``.
        """

        if not isinstance(krig_mesh, KrigingMesh):
            raise ValueError("You must provide a KrigingMesh object!")

        if (
            not isinstance(self.survey.bio_calc.transect_results_gdf, gpd.GeoDataFrame)
        ) and (
            "biomass_density_adult" not in self.survey.bio_calc.transect_results_gdf
        ):
            raise ValueError(
                "The areal biomass density must be calculated before running this routine!"
            )

        field_var_arr, field_samplevar_arr, field_mean_arr = self.run_kriging(
            krig_mesh.transformed_mesh_df["x_mesh"].values,
            krig_mesh.transformed_transect_df["x_transect"].values,
            krig_mesh.transformed_mesh_df["y_mesh"].values,
            krig_mesh.transformed_transect_df["y_transect"].values,
            self.survey.bio_calc.transect_results_gdf[
                "biomass_density_adult"
            ].values.flatten(),
        )

        # add corresponding mesh variables
        results_gdf = krig_mesh.mesh_gdf.copy(deep=True)

        # add the stratum number to the results
        results_gdf["stratum_num"] = pd.cut(
            results_gdf["centroid_latitude"],
            bins=[0.0]
            + list(self.survey.geo_strata_df["Latitude (upper limit)"])
            + [90.0],
            labels=list(self.survey.geo_strata_df["stratum_num"]) + [1],
            ordered=False,
        )

        # add adult biomass density Kriging results
        results_gdf["biomass_density_adult_mean"] = field_mean_arr
        results_gdf["biomass_density_adult_var"] = field_var_arr
        results_gdf["biomass_density_adult_samplevar"] = field_samplevar_arr

        # add area and adult biomass results
        results_gdf["cell_area_nmi2"] = (
            self.survey.params["kriging_A0"] * results_gdf["fraction_cell_in_polygon"]
        )
        results_gdf["biomass_adult"] = (
            results_gdf["biomass_density_adult_mean"] * results_gdf["cell_area_nmi2"]
        )

        self.survey.bio_calc.kriging_results_gdf = results_gdf

        # initialize male and female GeoDataFrames
        # TODO: do we want to include other columns here?
        self.survey.bio_calc.kriging_results_male_gdf = results_gdf[
            ["centroid_latitude", "centroid_longitude", "geometry", "stratum_num"]
        ].copy(deep=True)
        self.survey.bio_calc.kriging_results_female_gdf = results_gdf[
            ["centroid_latitude", "centroid_longitude", "geometry", "stratum_num"]
        ].copy(deep=True)

    def compute_kriging_variables(self) -> None:
        """
        Computes useful variables corresponding to values at each
        Kriging mesh point and assigns them to the GeoDataFrame
        ``self.survey.bio_calc.kriging_results_gdf``. For example,
        computes the ``abundance`` at each Kriging mesh point.
        """

        # initialize class object
        self.krig_bio_calc = ComputeKrigingVariables(self)

        # calculate and assign variables to Kriging results GeoDataFrames
        self.krig_bio_calc.set_variables()
