from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import json

from datetime import datetime
import pytz

@dataclass
class ImageryOptions:
    save_geojson: bool = False # save extracted shorelines to geojson
    save_plots: bool = False # plots all extracted shorelines in different colours
    cache_enabled: bool = False # Try loading <sitename>_output.pkl file to skip shoreline extraction
    skip_existing_jpg: bool = False # skip creating jpg that already exist (I don't think this is working)
    capture_skipped_jpgs: bool = False # save skipped jpg for debugging
    skip_jpg: bool = True # skip saving jpg altogether (saving jpg is not necessary for analysis)
    prompt_for_ideal_selection: bool = False

@dataclass
class AnalysisOptions:
    plot_transects: bool = False # plots all extracted shorelines and all transects
    plot_time_series: bool = False # saves time series of each transect (currently illegible for any reasonable number of transects)
    write_csv: bool = True # saves time series data to csv file (after outlier rejection)

@dataclass
class SlopeOptions:
    save_figures: bool = True # plots energy curves and slope spectrum
    cache_dir_name: str = "slope_estimation" # directory for slope plots

@dataclass
class TideOptions:
    reference_elevation: float = 0.0 # elevation of reference shoreline
    write_csv: bool = True # saves tidally corrected time series data to csv file
    beach_slope: Optional[float] = None # default beach slope for csv tidal correction if one not provided by user

@dataclass
class PlottingOptions: # transects_colored_by_trend (currently transects aren't visible)
    trend_min: float = -30.0 # set range for trends
    trend_max: float = 30.0
    cmap_name: str = "RdBu_r" # colour bar
    dpi: int = 300

@dataclass
class TimeSeriesOptions:
    """Tuning switches for time-series post-processing outputs."""
    write_csv: bool = False # would overwrite file made earlier in pipeline...
    save_seasonal_plots: bool = True # save plot for each transect with one point per season
    save_monthly_plots: bool = True # save plot for each transect with one point per month
    save_ma_plots: bool = True # save plot with individual observations and a 6month moving average


def print_options():
    print(ImageryOptions())
    print(AnalysisOptions())
    print(SlopeOptions())
    print(TideOptions())
    print(PlottingOptions())
    print(TimeSeriesOptions())

@dataclass
class Parameters:
    version = 1.2

    apply_tide_correction = True # False means skip slope estimation and tide correction
    
    # How much to put in log file
    # "none" = nothing - everything printed to terminal. Note: this is a string, not a None
    # "params" = parameters and options, other output printed to terminal
    # "all" = everything saved in log file
    logging_level = "params"

    #####################
    # Config
    #####################
    # Note: these parameters only affect downloads. Analysis is unaffected (it is performed on anything already downloaded)
    download_filters = {
        'dates': ["1984-01-01", "2027-01-01"], # range of dates of aquisitions to be downloaded
        'sat_list': ["L5", "L7", "L8", "L9", "S2"], # satellite missions to download images from
        # 'excluded_epsg_codes': ['32609'], # exclude images with given epsg codes
        # 'LandsatWRS': '055022', # specify a Landsat tile (WRS path/row)
        # 'S2tile': '09UVA', # specifies an S2 tile
        # 'months': [7, 8, 9, 10], # include only images taken in given months
        # 'skip_L7_SLC': True # skip L7 after Scan-Line-Correction failure
    }

    #####################
    # Imagery
    #####################
    shoreline_settings = {

        # preprocessing
        "cloud_mask_issue": False, # switch this parameter to True if sand pixels are masked (in black) on many images
        "pan_off": False, # True to switch pansharpening off for Landsat 7/8/9 imagery
        "s2cloudless_prob": 60, # Threshold to identify cloud pixels in the s2cloudless probability mask (s2 cloud mask is not 1 and 0, but a probability [0,100))

        # extraction settings
        "cloud_thresh": 0.5, # percentage of image that can be covered by cloud
        "dist_clouds": 30, # distance in metres defining a buffer around cloudy pixels where the shoreline cannot be mapped
        "min_length_sl": 500, # minimum length of shoreline perimeter to be kept (in meters)
        "max_dist_ref" : 250, # maximum distance from the reference shoreline in meters

        # manual detection (untested)
        "check_detection": False, # lets user manually accept/reject the mapped shorelines
        "adjust_detection": False, # lets user adjust the detected shorelines with a slide bar.

        # classifier (only used for very sandy beaches)
        "min_beach_area": 1000, # minimum number of pixels that have to be connected to belong to the SAND class
        "sand_color": "default", # classification model: 'default', 'latest', 'dark' (for grey/black sand beaches) or 'bright' (for white sand beaches)

        # plotting
        "plot_mndwi": False, # plot histograms of MNDWI values for each image
        "save_detection_plots": True, # plot RGB, pixel classification, MNDWI, and extracted shoreline
        "plot_cloud_cover": True, # plot histogram of cloud cover percentages of each image

        # saving pkl files
        "save_sat_rgb": False, # must be True if plot_sat
    }

    #####################
    # Analysis
    #####################
    transect_settings = {

        # collider settings (note how these interact with max_dist_ref)
        "along_dist": 35, # how far a point can be orthogonally to transect line
        "past_dist": 300, # distance a shoreline points can be past end of transect and be counted as an intersection
        "min_chainage": -150, # furthest landward of the transect origin that an intersection is accepted
        
        # dispersion thresholds
        "min_points": 3, # minimum number of points to calculate an intersections
        "max_std": 15, # maximum standard deviation of intersections per transect (exceptions are dealt with according to multiple_inter)
        "max_range": 30, # maximum range of intersections per transect (exceptions are dealt with according to multiple_inter)

        # clustering shoreline selection settings
        "CASS": True, # use shoreline selection algorithm
        "clustering_threshold": 20, # minimum gap between adjacent intersections needed to start new cluster
        
        # clustering shoreline selection plotting
        "transects_to_plot": [], # plot all intersections for transects with these names
        "plot_entire_shoreline": False, # add plot showing the entire shoreline (not implemented for CASS_V2)
        "plot_1d": False, # add plot showing projected intersection points (not implemented for CASS_V2)
        "plot_sat": False, # add satellite image as basemap

        "plot_rejection_counts": True, # plot why intersections were rejected, for each transect and each shoreline (before outlier rejection)
    }

    outlier_settings = {
        "max_cross_change": 40, # maximum cross-shore change allowed between consecutive timesteps
        "otsu_threshold": [-0.5, 0], # min and max intensity threshold use for contouring the shoreline
        "plot_fig": True, # display time series before and after outlier rejection for each transect
    }

    #####################
    # Slope Estimation
    #####################
    # date range used specifically for slope estimation. Should have at least 2 satellite missions available
    slope_estimation_date_range = [
        pytz.utc.localize(datetime(2020, 1, 1)),
        pytz.utc.localize(datetime(2025, 1, 1)),
    ]
    tide_timestep = 900 # compute tide level in date range at intervals of timestep seconds

    slope_settings = {
        'plot_fig': SlopeOptions().save_figures, # save slope estimation figures

        # beach slopes generated from slope_min to slope_max at intervals of delta_slope
        'slope_min': 0.005,
        'slope_max': 0.4,
        'delta_slope': 0.005,

        # parameters for slope estimation. Do not touch unless you understand the process
        'n0': 50,
        'freq_cutoff': 1. / (24 * 3600 * 30),  # 30-day frequency
        'delta_f': 100 * 1e-10,
        'prc_conf': 0.05, # confidence 
        'n_days': 8
    }

    # this is also used in tide.py
    default_slope = 0.1 # default slope used when error occurs in slope estimation

    #######################
    # Timeseries
    #######################
    # give entire path to put seasonal and monthly trend plots, and where the geojson points to
    # if None, then puts everything in output folder
    # Intended for putting outputs of many sites in one place, for easier webmap creation
    alternate_trend_plot_dir = None

    # minimum number of points in time series to create plots and calculate trends
    # trend set to nan if insufficient points
    # should be >= 1
    min_chainage_size = 10


    # print all variables in class in alphabetical order
    # written so that it doesn't need updating every time parameters is tweaked
    def print_params(self):
        atts = [attr for attr in dir(self) if not callable(getattr(self, attr)) and not attr.startswith("__")]
        
        for att in atts:
            val = getattr(self, att)

            if type(val) == dict:
                print(f"{att}: ", end="")
                print(json.dumps(val, indent=4))
            else:
                print(f"{att}: {getattr(self, att)}")