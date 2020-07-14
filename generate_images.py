#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" Code adapted from the Jupyter notebook

Most of the code in this file has been copied and pasted from the
`generate_tweets.ipynb` notebook file. To run in parallel:

    cat urbanheat_for_models.csv |
        tail -n +2 |
        cut -d "," -f 1 |
        xargs -n 20 -P 16 ./generate_images.py

"""

import functools
import os
import re
import typing

import contextily
import geopandas
import pandas
import shapely.geometry
import tqdm.auto as tqdm
from matplotlib import colors, cm, pyplot

contextily.tile.memory.store_backend.location = "CONTEXTILY_CACHE"
tqdm.tqdm.pandas()

T_DataFrame = pandas.core.frame.DataFrame
T_Series = pandas.core.series.Series

# hacky way to typedef figure and axis; axis cannot be declared directly
(figure, axis) = pyplot.subplots()
T_Figure = type(figure)
T_Axis = type(axis)
pyplot.close()

def denormalize(normalized_lst: float) -> float:
    """ Denormalize LST data. """
    return 44 * normalized_lst + 72.4

gdf_roads = geopandas.read_file("shapefiles/roads_fin_clust_2018_11142019.shp")\
    .to_crs({"init": "epsg:3857"}) # to simplify plotting

# updated road attributes
df_roads = pandas.read_csv("Roads.2019.csv")

# neighborhood sections (`NBHDS89_` column)
gdf_bns = geopandas.read_file("shapefiles/2010_BNS_by_NBHDS89_Shape.shp")\
    .to_crs(gdf_roads.crs) # to match gdf_roads

# neighborhoods (`Name` column)
gdf_neighborhoods = geopandas.read_file("shapefiles/Boston_Neighborhoods.shp")\
    .to_crs(gdf_roads.crs) # to match gdf_roads

df_urbanheat = pandas.read_csv("urbanheat_for_models.csv")
for lst_column in ["LST_CT", "LST_weighted"]:
    df_urbanheat[lst_column] = df_urbanheat[lst_column].apply(denormalize)

df_parcels = pandas.read_csv("LandParcels.2019.csv")

# each dataframe is iteratively left merged
gdf_merged = geopandas.GeoDataFrame(functools.reduce(
    lambda left, right: pandas.merge(
        left[left.columns.difference(right.columns).to_list() + ["TLID"]],
        right,
        how="left",
        on="TLID"
    ),
    [df_urbanheat, df_roads, gdf_roads]
))
gdf_merged.crs = gdf_roads.crs

gdf_roads_nodata = gdf_roads[~gdf_roads["TLID"].isin(gdf_merged["TLID"])]

# set of functions to extract address ranges from a list of full addresses

def mostly_a_number(string: str) -> bool:
    """ Return True if a string is mostly composed of integer characters. """
    return sum(1 for char in string if char.isdigit()) > 0.5

def natural_keys(string: str) -> typing.List[typing.Union[str, int]]:
    """ Break up a string into a list of contiguous numbers and strings, in
    such a way that a list comparison can perform natural sorts.

    Credit: https://stackoverflow.com/a/5967539
    """
    return [
        int(char)
        if char.isdigit()
        else char
        for char in re.split(r"(\d+)", string)
    ]

def address_numbers(full_address: str) -> typing.List[str]:
    """ Extract strings corresponding to different house numbers in an address.

    Here, we define house numbers as strings consisting mostly of numbers. In
    this way, we are able to capture non-integer numbers like "10A", "5E", etc.
    """
    return [
        address_part
        # we drop the zipcode here by taking only indices [:-1]
        for address_part in full_address.replace("-", " ").split()[:-1]
        if mostly_a_number(address_part)
    ]

def address_range(addresses: typing.List[str]) -> str:
    """ Extract the address range for a given list of addresses. """
    numbers = sorted(
        set(
            address_number
            for address in addresses
            for address_number in address_numbers(address)
        ),
        key=natural_keys
    )
    if len(numbers) == 0:
        return ""
    elif len(numbers) == 1:
        return numbers[0]
    else:
        return "{}-{}".format(numbers[0], numbers[-1])

def address_range_from_tlid(tlid: int) -> str:
    """ Given a TLID, extract the address range. """
    return address_range(df_parcels[df_parcels["TLID"] == tlid]["full_address"])

def make_square(axis):
    """ Force an axis to be square by having the smaller dimension equal the
    size of the larger dimension.

    Changing the aspect ratio can distort basemaps; this method does not.
    """
    xlim = axis.get_xlim()
    ylim = axis.get_ylim()
    width = xlim[1] - xlim[0]
    height = ylim[1] - ylim[0]
    if width > height: # make taller
        center_y = (ylim[0] + ylim[1])/2
        axis.set_ylim([
            center_y - width/2,
            center_y + width/2
        ])
    else: # make wider
        center_x = (xlim[0] + xlim[1])/2
        axis.set_xlim([
            center_x - height/2,
            center_x + height/2
        ])

column = "LST_weighted"
margin = 2.5 # times the size of the original figure
basemap = contextily.providers.CartoDB.Positron
inset_basemap = contextily.providers.CartoDB.PositronNoLabels
inset_linewidth = 5
inset_position = [0.55, 0.05, 0.4, 0.6] # x y w h

def generate_image(street: T_Series) -> typing.Tuple[T_Figure, T_Axis]:
    # forcing the aspect ratio slightly resizes the inset. i'm not sure how to
    # get the exact figure positions of the inset after resize, so a correction is
    # manually determined by trial and error and then applied.
    inset_adjust = 0.01

    # initialize colors
    colormap = cm.get_cmap("magma", 12)
    normalize = colors.Normalize(
        vmin=gdf_merged[column].min(),
        vmax=gdf_merged[column].max()
    )

    # initialize figure
    (figure, axis) = pyplot.subplots(figsize=(14, 7))

    # colorbar
    colorbar = figure.colorbar(
        cm.ScalarMappable(norm=normalize, cmap=colormap),
        ax=axis
    )
    colorbar.set_label(
        "Summer land surface temperature 2002-2008 [°F]",
        rotation=270,
        labelpad=10
    )

    # main plot
    gdf_merged.plot(ax=axis, column=column, cmap=colormap, legend=False)

    # create extra room on the right for the inset
    xlim = axis.get_xlim()
    axis.set_xlim([xlim[0], xlim[1] + 2e4])

    # inset plot
    inset = axis.inset_axes(inset_position)
    gdf_plot = geopandas.GeoDataFrame(street).T
    gdf_plot.crs = gdf_roads.crs
    gdf_plot.plot(
        ax=inset, color=colormap(normalize(street[column])),
        linewidth=inset_linewidth, zorder=2
    )
    inset.margins(x=margin, y=margin)

    # roads for which we have no data. we need to disable autoscale first because
    # these functions contain data far from the road in question
    inset.autoscale(False)
    gdf_merged.plot(
        ax=inset, column=column, cmap=colormap,
        alpha=0.3, linewidth=inset_linewidth, zorder=1
    )
    gdf_roads_nodata.plot(
        ax=inset, color="black", linestyle="--",
        alpha=0.3, linewidth=4, zorder=1, label="no data"
    )
    inset.legend()

    # set inset to be equal ratio (other plotting functions can change this, so we
    # run it after all plotting functions that interact with the inset). we also
    # need to update the xlim and ylim at this point
    make_square(inset)
    inset_xlim = inset.get_xlim()
    inset_ylim = inset.get_ylim()

    # rectangle showing the location of the inset
    # transformer credit: https://stackoverflow.com/a/40475221
    axis_to_data = axis.transAxes + axis.transData.inverted()
    inset_coords_bottomleft = (inset_xlim[0], inset_ylim[0])
    inset_coords_topleft = (inset_xlim[0], inset_ylim[1])
    inset_pos_bottomleft = axis_to_data.transform(
        (inset_position[0] + inset_adjust, inset_position[1])
    )
    inset_pos_topleft = axis_to_data.transform(
        (inset_position[0] + inset_adjust, inset_position[1] + inset_position[3])
    )
    gdf_inset_location = geopandas.GeoDataFrame([{
        "geometry": shapely.geometry.Polygon([
            inset_coords_bottomleft,
            inset_coords_topleft,
            inset_pos_topleft,
            inset_pos_bottomleft
        ])
    }])
    gdf_inset_location.plot(ax=axis, color="black", zorder=3, alpha=0.5)

    # remove all coordinate ticks
    axis.set_xticks([])
    axis.set_yticks([])
    inset.set_xticks([])
    inset.set_yticks([])

    # text
    axis.text(
        -7892500, 5220000,
        "The average land surface temperature for",
        fontsize=12,
        horizontalalignment="center"
    )
    axis.text(
        -7892500, 5218400,
        "{house_numbers} {street_name}".format(
            house_numbers=address_range_from_tlid(street["TLID"]),
            street_name=street["FULLNAM"]
        ),
        fontsize=22,
        horizontalalignment="center"
    )
    axis.text(
        -7892500, 5217000,
        "was",
        fontsize=15,
        horizontalalignment="center"
    )
    axis.text(
        -7892500, 5214500,
        "{:.1f}°F".format(street["LST_weighted"]),
        fontsize=40,
        horizontalalignment="center"
    )
    axis.text(
        -7892500, 5213000,
        "in the summers from 2002-2008",
        fontsize=15,
        horizontalalignment="center"
    )

    # basemaps
    contextily.add_basemap(ax=axis, source=basemap)
    contextily.add_basemap(ax=inset, source=inset_basemap)

    # the above basemap code may have resized the inset
    inset.set_xlim(inset_xlim)

    pyplot.tight_layout()

    return (figure, axis)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("tlids", nargs="+")
    args = parser.parse_args()

    if not os.path.isdir("output"):
        os.makedirs("output")

    n_to_sample = 3
    for tlid in args.tlids:
        street = gdf_merged[gdf_merged["TLID"] == int(tlid)].iloc[0]
        output_file = "output/{}.png".format(street["TLID"])
        if os.path.isfile(output_file):
            continue

        (figure, axis) = generate_image(street)

        # note that the inset position is slightly off in Jupyter; it appears as
        # intended on the exported image
        pyplot.savefig(output_file)
        pyplot.close()