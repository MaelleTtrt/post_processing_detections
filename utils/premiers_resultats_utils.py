import datetime
from typing import Iterable
from pathlib import Path
import pandas as pd
import numpy as np
import easygui
import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.dates import MonthLocator

from def_func import (
    t_rounder,
    suntime_hour,
    get_duration,
    read_yaml,
    load_detections,
    get_datetime_format,
)
from collections import Counter
import seaborn as sns
from scipy.stats import pearsonr
import def_func


def load_parameters_from_yaml(
    file: Path,
) -> (
    pd.DataFrame,
    list[int],
    list[str],
    list[str],
    list[int],
    pd.Timestamp,
    pd.Timestamp,
    list[datetime.timezone],
):
    """Loads parameters from yaml

    Parameters
    ----------
    file: Path to yaml file

    Returns
    -------
    df : APLOSE formatted detections
    time_bin:  list, time bin(s) in seconds
    annotators: list of annotators
    labels: list of labels
    fmax: list of maximum frequencies
    datetime_begin: pd.Timestamp
    datetime_end: pd.Timestamp
    tz: timezone
    """
    parameters = read_yaml(file=file)

    df = pd.DataFrame()
    for f in parameters:
        df = pd.concat([df, load_detections(**parameters[f])], ignore_index=True)

    time_bin = list(set(df["end_time"]))
    fmax = list(set(df["end_frequency"]))
    annotators = sorted(list(set(df["annotator"])))
    labels = sorted(list(set(df["annotation"])))

    if len(list(set([dt.tz for dt in df["start_datetime"]]))) > 1:
        df["start_datetime"] = [dt.tz_convert("UTC") for dt in df["start_datetime"]]
        df["end_datetime"] = [dt.tz_convert("UTC") for dt in df["end_datetime"]]

    return (
        df.sort_values(by="start_datetime"),
        time_bin,
        annotators,
        labels,
        fmax,
        df["start_datetime"].iloc[0],
        df["end_datetime"].iloc[-1],
        df["start_datetime"].iloc[0].tz,
    )


def select_tick_resolution(
    ax: str, default: int, lowerbound: int, upperbound: int
) -> int:
    return easygui.integerbox(
        msg=f"Choose the {ax}-axis tick resolution",
        title="Tick resolution",
        default=default,
        lowerbound=lowerbound,
        upperbound=upperbound,
    )


def select_reference(param: Iterable, param_str: str = ""):
    """Selection of a reference parameter (label, annotator...) from a list

    Parameters
    ----------
    param : Iterable
        list of the choices
    param_str: str
        message to display

    Returns
    -------
    the user-defined reference parameter
    """
    if len(list(set(param))) > 1:
        selection = easygui.buttonbox(
            msg=f"{param_str} selection",
            title="Parameter selection",
            choices=[str(elem) for elem in list(set(param))],
        )
    else:
        selection = list(set(param))[0]

    if not selection:
        raise TypeError("select_reference() has been cancelled")

    return selection


def set_plot_resolution(
    time_bin: int,
    start: pd.Timestamp,
    stop: pd.Timestamp,
) -> (pd.DatetimeIndex, str, int, mpl.dates.DayLocator):
    """Compute the time_vector for a user-defined resolution and select appropriate date ticks and datetime format for plots
    Parameters
    ----------
    time_bin : int, length in seconds of a time bin, it is similar to the precision of the future plots
    start : pd.Timestamp, begin datetime
    stop : pd.Timestamp, end datetime

    Returns
    -------
    datetime_index : pd.DatetimeIndex, computed timestamps according to user-defined resolution
    y_axis_plot_legend : str, string used for the y-axis legend
    number_max_of_annotation : maximum number of annotations possible according to resolution and time bin
    date_interval : mdates x-ticks resolution
    """

    resolution_bin = get_duration(msg="Enter the x-axis bin resolution")
    resolution_x_ticks = get_duration(
        msg="Enter the x-axis tick resolution", default="2h"
    )

    # if type(resolution_x_ticks) == int:
    #     date_interval = mdates.SecondLocator(interval=resolution_x_ticks)
    # elif resolution_x_ticks.base == 'MS':
    #     date_interval = mdates.MonthLocator(interval=resolution_x_ticks)
    date_interval = resolution_x_ticks

    number_max_of_annotation = int(resolution_bin / time_bin)
    datetime_index = pd.date_range(
        start=t_rounder(t=start, res=resolution_bin),
        end=t_rounder(t=stop, res=resolution_bin),
        freq=str(resolution_bin) + "s",
    )

    resolution_bin_str = _get_resolution_str(resolution_bin)
    time_bin_str = _get_resolution_str(time_bin)
    y_axis_plot_legend = (
        f"Detections\n(resolution: {time_bin_str} - bin size: {resolution_bin_str})"
    )

    return (
        datetime_index,
        y_axis_plot_legend,
        number_max_of_annotation,
        date_interval,
    )


def set_y_axis(ax: mpl.axes, max_annotation_number: int):
    """Changes ax properties whether the plot is visualized in percentage or in raw values

    Parameters
    ----------
    ax
    max_annotation_number
    resolution
    """
    choice_percentage = easygui.buttonbox(
        msg="Do you want your scripts plot in percentage or in raw values ?",
        choices=["percentage", "raw values"],
    )

    resolution = easygui.integerbox(
        msg=f"Select a y-ticks resolution\n(mode='{choice_percentage}' / max_annotation_number={max_annotation_number})",
        title="Plot resolution",
        default=10,
        lowerbound=1,
        upperbound=1440,
    )

    # change the y scale
    if choice_percentage == "percentage":
        bars = np.arange(0, 101, resolution)
        y_pos = [max_annotation_number * pos / 100 for pos in bars]

        if isinstance(ax, Iterable):
            [a.set_yticks(y_pos, bars) for a in ax]
            [a.set_ylabel("%") for a in ax]
        else:
            ax.set_yticks(y_pos, bars)
            ax.set_ylabel("%")
    else:
        if isinstance(ax, Iterable):
            [
                a.set_yticks(
                    np.arange(0, max_annotation_number + resolution, resolution)
                )
                for a in ax
            ]
            [a.set_ylabel("N") for a in ax]
        else:
            ax.set_yticks(np.arange(0, max_annotation_number + resolution, resolution))
            ax.set_ylabel("N")

    # set y-axis limit
    if isinstance(ax, Iterable):
        y_max = [
            max([patch.get_height() for patch in ax[i].patches]) for i in range(len(ax))
        ]
        [a.set_ylim([0, min(int(1.4 * max(y_max)), max_annotation_number)]) for a in ax]
    else:
        y_max = max([patch.get_height() for patch in ax.patches])
        ax.set_ylim([0, min(int(1.4 * y_max), max_annotation_number)])

    return choice_percentage


def overview_plot(df: pd.DataFrame):
    """Overview of an APLOSE formatted dataframe

    Parameters
    ----------
    df: pd.DataFrame, APLOSE formatted result DataFrame with detections and associated timestamps
    """
    summary_label = (
        df.groupby("annotation")["annotator"].apply(Counter).unstack(fill_value=0)
    )
    summary_annotator = (
        df.groupby("annotator")["annotation"].apply(Counter).unstack(fill_value=0)
    )

    print(f"\n- Overview of the detections -\n\n {summary_label}")

    fig, ax = plt.subplots(2, 1)
    ax[0] = summary_label.plot(kind="bar", ax=ax[0], edgecolor="black", linewidth=1)
    ax[1] = summary_annotator.plot(kind="bar", ax=ax[1], edgecolor="black", linewidth=1)

    for a in ax:
        # legend
        a.legend(loc="best", frameon=1, framealpha=0.6)
        # ticks
        a.tick_params(axis="both", rotation=0)
        a.set_ylabel("Number of annotated calls")
        # y-grids
        a.yaxis.grid(color="gray", linestyle="--")
        a.set_axisbelow(True)

    # labels
    ax[0].set_xlabel("Labels")
    ax[1].set_xlabel("Annotator")

    # titles
    ax[0].set_title("Number of annotations per label")
    ax[1].set_title("Number of annotations per annotator")

    plt.tight_layout()
    plt.show()

    return


def plot_hourly_detection_rate(
    df: pd.DataFrame,
    lat: float,
    lon: float,
    date_format: str = "%H:%M",
    show_rise_set: bool = True,
):
    """Computes the hourly detection rate for an APLOSE formatted result DataFrame

    Parameters
    ----------
    df : pd.DataFrame, APLOSE formatted result DataFrame with detections and associated timestamps
    lat: float, latitude
    lon: float, longitude
    date_format: str, default '%H:%M'
    show_rise_set : bool, default True, display the sunrise and sunset lines
    """
    datetime_begin = df["start_datetime"].iloc[0]
    datetime_end = df["end_datetime"].iloc[-1]
    tz = datetime_begin.tz

    bin = select_reference(df["end_time"], "time bin")

    # compute sunrise and sunset decimal hour at the dataset location
    sunrise, sunset, _, _, _, _ = suntime_hour(
        start=datetime_begin, stop=datetime_end, lat=lat, lon=lon
    )

    df["date"] = [ts.normalize() for ts in df["start_datetime"]]
    df["hour"] = [ts.hour for ts in df["start_datetime"]]

    det_groupby = df.groupby(["date", "hour"]).size()
    idx_day_groupby = det_groupby.index.get_level_values(0)
    idx_hour_groupby = det_groupby.index.get_level_values(1)

    dates = pd.date_range(
        datetime_begin.normalize(), datetime_end.normalize(), freq="D"
    )
    M = np.zeros((24, len(dates)))
    for idx_j, j in enumerate(dates):
        # Search for detection in day = j
        f = [idx for idx, det in enumerate(idx_day_groupby) if det == j]
        if f:
            for ff in f:
                hour = idx_hour_groupby[ff]
                M[int(hour), idx_j] = det_groupby.iloc[ff]

    # plot
    fig, ax = plt.subplots()
    im = ax.imshow(
        M,
        extent=[datetime_begin, datetime_end, 0, 24],
        vmin=0,
        vmax=3600 / bin,
        aspect="auto",
        origin="lower",
    )
    # colorbar
    cbar = fig.colorbar(im)
    cbar.ax.set_ylabel(f"{str(bin)}s bins positive to detection")

    if show_rise_set:
        plt.plot(dates, sunrise, color="darkorange", linewidth=1)
        plt.plot(dates, sunset, color="royalblue", linewidth=1)

    # axes settings
    ax.xaxis_date()
    resolution_x_ticks = get_duration(
        msg="Enter the x-axis tick resolution", default="2h"
    )
    ax.xaxis.set_major_locator(mdates.SecondLocator(interval=resolution_x_ticks))
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt=date_format, tz=tz))
    ax.set_ylabel("Hour")
    ax.set_xlabel("Date")
    plt.xlim(datetime_begin, datetime_end)
    plt.tight_layout()
    plt.show()

    return


def scatter_detections(
    df: pd.DataFrame,
    lat: float,
    lon: float,
    date_format: str = "%H:%M",
    show_rise_set: bool = True,
):
    """Plot scatter of the detections from an APLOSE formatted DataFrame.
    Additionally, sunrise and sunset lines can be plotted if show_rise_set is set to True (default value)

    Parameters
    ----------
    df : pd.DataFrame, APLOSE formatted result DataFrame with detections and associated timestamps
    lat : float, latitude
    lon : float, longitude
    date_format : string template, default '%H:%M'
    show_rise_set : bool, default True, display the sunrise and sunset lines
    """
    datetime_begin = df["start_datetime"].iloc[0]
    datetime_end = df["end_datetime"].iloc[-1]
    tz = datetime_begin.tz

    # compute sunrise and sunset decimal hour at the dataset location
    hour_sunrise, hour_sunset, _, _, _, _ = suntime_hour(
        start=datetime_begin, stop=datetime_end, lat=lat, lon=lon
    )

    dates = pd.date_range(datetime_begin.date(), datetime_end.date(), freq="D")

    # decimal hours of detections
    hour_det = [
        ts.hour + ts.minute / 60 + ts.second / 3600 for ts in df["start_datetime"]
    ]

    # plot
    fig, ax = plt.subplots()
    plt.scatter(
        df["start_datetime"], hour_det, marker="x", linewidths=1, color="silver"
    )
    if show_rise_set:
        plt.plot(dates, hour_sunrise, color="darkorange")
        plt.plot(dates, hour_sunset, color="royalblue")

    # axes settings
    plt.xlim(datetime_begin, datetime_end)
    plt.ylim(0, 24)

    resolution_x_ticks = get_duration(
        msg="Enter the x-axis tick resolution", default="2h"
    )
    ax.xaxis.set_major_locator(mdates.SecondLocator(interval=resolution_x_ticks))
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt=date_format, tz=tz))
    ax.grid(color="k", linestyle="-", linewidth=0.2)
    ax.set_ylabel("Hour")
    ax.set_xlabel("Date")

    # title
    plt.title(
        f"Time of detections within each day for dataset {select_reference(df['dataset'])}"
    )

    plt.tight_layout()
    plt.show()

    return


def single_plot(df: pd.DataFrame):
    """Plot the detections of an APLOSE formatted DataFrame for a single label

    Parameters
    ----------
    df: pd.DataFrame, APLOSE formatted result DataFrame with detections and associated timestamps
    """
    # selection of the references parameters
    datetime_begin = df["start_datetime"].iloc[0]
    datetime_end = df["end_datetime"].iloc[-1]
    annotators = list(set(df["annotator"]))
    annot_ref = select_reference(annotators, "annotator")
    label_ref = select_reference(
        df[df["annotator"] == annot_ref]["annotation"], "label"
    )
    time_bin_ref = select_reference(
        df[df["annotator"] == annot_ref]["end_time"], "time bin"
    )

    # set plot resolution
    time_vector, y_label_legend, n_annot_max, date_locator = set_plot_resolution(
        time_bin=time_bin_ref, start=datetime_begin, stop=datetime_end
    )

    df_1annot_1label = df[
        (df["annotator"] == annot_ref) & (df["annotation"] == label_ref)
    ]

    # plot
    fig, ax = plt.subplots()
    [hist_y, hist_x, _] = ax.hist(
        df_1annot_1label["start_datetime"],
        bins=time_vector,
    )

    # title
    plt.title(f"annotator: {annot_ref}\nlabel: {label_ref}")

    # axes settings
    ax.xaxis.set_major_locator(date_locator)
    date_formatter = mdates.DateFormatter(
        fmt=get_datetime_format(), tz=datetime_begin.tz
    )
    ax.xaxis.set_major_formatter(date_formatter)
    plt.xlim(time_vector[0], time_vector[-1])
    ax.grid(linestyle="--", linewidth=0.2, axis="both")
    ax.set_ylabel(y_label_legend)
    set_y_axis(ax, n_annot_max)

    plt.tight_layout()
    plt.show()

    return


def multilabel_plot(df: pd.DataFrame):
    """Plot the detections of an APLOSE formatted DataFrame for a all labels

    Parameters
    ----------
    df: pd.DataFrame, APLOSE formatted result DataFrame with detections and associated timestamps
    """
    datetime_begin = df["start_datetime"].iloc[0]
    datetime_end = df["end_datetime"].iloc[-1]
    annotators = list(set(df["annotator"]))
    annot_ref = select_reference(annotators, "annotator")
    time_bin_ref = select_reference(
        df[df["annotator"] == annot_ref]["end_time"], "time bin"
    )
    list_labels = list(set(df[df["annotator"] == annot_ref]["annotation"]))

    if not len(list_labels) > 1:
        raise ValueError(
            f"Only {str(len(list_labels))} labels detected, multilabel plot cancelled"
        )

    time_vector, y_label_legend, n_annot_max, date_locator = set_plot_resolution(
        time_bin=time_bin_ref,
        start=datetime_begin,
        stop=datetime_end,
    )

    fig, ax = plt.subplots(
        nrows=len(list_labels),
    )
    y_max = []
    date_formatter = mdates.DateFormatter(
        fmt=get_datetime_format(), tz=datetime_begin.tz
    )
    for i, label in enumerate(list_labels):

        df_1annot_1label = df[
            (df["annotator"] == annot_ref) & (df["annotation"] == label)
        ]

        ax[i].hist(
            df_1annot_1label["start_datetime"],
            bins=time_vector,
            linewidth=1,
        )

        ax[i].set_title(label)
        if type(date_locator) == int:
            ax[i].xaxis.set_major_locator(mdates.SecondLocator(interval=date_locator))
        elif date_locator.base == "MS":
            ax[i].xaxis.set_major_locator(mdates.MonthLocator(interval=date_locator.n))
        else:
            raise ValueError("date locator not supported")

        ax[i].xaxis.set_major_formatter(date_formatter)
        ax[i].set_xlim(time_vector[0], time_vector[-1])
        ax[i].grid(linestyle="--", linewidth=0.2, axis="both")

    set_y_axis(ax, n_annot_max)

    fig.suptitle(f"Annotator : {annot_ref}")
    fig.supylabel(y_label_legend)
    plt.tight_layout()
    plt.show()

    return


def multiuser_plot(df: pd.DataFrame):

    df = df.sort_values(by="start_datetime")
    datetime_begin = df["start_datetime"].iloc[0]
    datetime_end = df["end_datetime"].iloc[-1]
    annotators = list(set(df["annotator"]))

    if len(annotators) < 2:
        raise ValueError("Only 1 annotator detected, multiuser plot cancelled")

    annot_ref1 = select_reference(annotators, "annotator 1")
    annot_ref2 = select_reference(
        [elem for elem in annotators if elem != annot_ref1], "annotator 2"
    )

    label_ref1 = select_reference(
        df[df["annotator"] == annot_ref1]["annotation"], "label 1"
    )
    if label_ref1 not in list(set(df[df["annotator"] == annot_ref2]["annotation"])):
        label_ref2 = select_reference(
            df[df["annotator"] == annot_ref2]["annotation"], "label 2"
        )
    else:
        label_ref2 = label_ref1

    time_bin_ref1 = select_reference(
        df[df["annotator"] == annot_ref1]["end_time"], "time bin 1"
    )
    time_bin_ref2 = select_reference(
        df[df["annotator"] == annot_ref2]["end_time"], "time bin 2"
    )

    if time_bin_ref1 != time_bin_ref1:
        raise ValueError(
            f"The timebin of the detections {annot_ref1}/{label_ref1} is {time_bin_ref1}s"
            f" whereas the timebin for {annot_ref2}/{label_ref2} is {time_bin_ref2}s"
        )
    else:
        time_bin_ref = time_bin_ref1

    # set plot resolution
    time_vector, y_label_legend, n_annot_max, date_locator = set_plot_resolution(
        time_bin=time_bin_ref,
        start=datetime_begin,
        stop=datetime_end,
    )

    df1_1annot_1label = df[
        (df["annotator"] == annot_ref1) & (df["annotation"] == label_ref1)
    ]
    df2_1annot_1label = df[
        (df["annotator"] == annot_ref2) & (df["annotation"] == label_ref2)
    ]

    fig, ax = plt.subplots(1, 2, gridspec_kw={"width_ratios": [8, 2]})

    hist_plot = ax[0].hist(
        [df1_1annot_1label["start_datetime"], df2_1annot_1label["start_datetime"]],
        bins=time_vector,
        label=[annot_ref1, annot_ref2],
        lw=10,
    )
    primary_legend = ax[0].legend(loc="best")
    ax[0].add_artist(primary_legend)

    fig.suptitle(f"[{annot_ref1}/{label_ref1}] VS [{annot_ref2}/{label_ref2}]")
    fig.supylabel(y_label_legend)

    # axes settings
    if type(date_locator) == int:
        ax[0].xaxis.set_major_locator(mdates.SecondLocator(interval=date_locator))
    elif date_locator.base == "MS":
        ax[0].xaxis.set_major_locator(mdates.MonthLocator(interval=date_locator.n))
    else:
        raise ValueError("date locator not supported")

    date_formatter = mdates.DateFormatter(
        fmt=get_datetime_format(), tz=datetime_begin.tz
    )
    ax[0].xaxis.set_major_formatter(date_formatter)
    ax[0].set_xlim(time_vector[0], time_vector[-1])
    ax[0].grid(linestyle="--", linewidth=0.2, axis="both")
    ax[0].set_ylabel(y_label_legend)
    set_y_axis(ax[0], n_annot_max)
    ax[0].set_ylim(0, min(int(1.2 * hist_plot[0].max()), 100))
    ax[0].grid(linestyle="--", linewidth=0.2, axis="both")

    # accord inter-annot
    list1 = list(df1_1annot_1label["start_datetime"])
    list2 = list(df2_1annot_1label["start_datetime"])

    unique_annotations = len([elem for elem in list1 if elem not in list2]) + len(
        [elem for elem in list2 if elem not in list1]
    )
    common_annotations = len([elem for elem in list1 if elem in list2])
    agreement = common_annotations / (unique_annotations + common_annotations)
    ax[0].text(
        0.05, 0.9, f"agreement={100 * agreement:.0f}%", transform=ax[0].transAxes
    )

    # scatter
    df_corr = pd.DataFrame(
        hist_plot[0] / n_annot_max, index=[annot_ref1, annot_ref2]
    ).transpose()
    sns.scatterplot(x=df_corr[annot_ref1], y=df_corr[annot_ref2], ax=ax[1])

    z = np.polyfit(df_corr[annot_ref1], df_corr[annot_ref2], 1)
    p = np.poly1d(z)
    plt.plot(df_corr[annot_ref1], p(df_corr[annot_ref1]), lw=1)

    ax[1].set_xlabel(f"{annot_ref1}\n{label_ref1}")
    ax[1].set_ylabel(f"{annot_ref2}\n{label_ref2}")
    # ax[1].set_xlim(0, 1)
    # ax[1].set_ylim(0, 1)
    ax[1].grid(linestyle="-", linewidth=0.2, axis="both")

    r, p = pearsonr(df_corr[annot_ref1], df_corr[annot_ref2])
    ax[1].text(0.05, 0.9, f"R²={r * r:.2f}", transform=ax[1].transAxes)

    plt.tight_layout()
    plt.show()

    return


def plot_detection_timeline(df: pd.DataFrame):
    """Plot detections on a timeline

    Parameters
    ----------
    df: pd.DataFrame, APLOSE formatted DataFrame
    """
    labels = sorted(list(set(df["annotation"])))

    fig, ax = plt.subplots()

    for i, label in enumerate(labels[::-1]):
        time_det = df[(df["annotation"] == label)]["start_datetime"].to_list()
        l_data = len(time_det)
        x = np.ones((l_data, 1), int) * i
        plt.scatter(time_det, x, s=12)

    xtick_resolution = def_func.get_duration(
        msg="Enter x-tick resolution", default="1d"
    )
    locator = mdates.SecondLocator(interval=xtick_resolution)
    ax.xaxis.set_major_locator(locator)

    datetime_format = def_func.get_datetime_format(
        msg="Enter x-tick format", default="%d/%m"
    )
    formatter = mdates.DateFormatter(datetime_format)
    ax.xaxis.set_major_formatter(formatter)

    plt.grid(color="k", linestyle="-", linewidth=0.2)
    ax.set_yticks(np.arange(0, len(labels), 1))
    ax.set_yticklabels(labels[::-1])
    ax.set_xlabel("Date")
    plt.xlim(
        df["start_datetime"].min().normalize(),
        df["end_datetime"].max().normalize() + pd.Timedelta(days=1),
    )

    plt.tight_layout()
    plt.show()

    return


def _map_datetimes_to_vector(df: pd.DataFrame, timestamps: [int]):
    """Maps datetime ranges to a binary vector based on overlap with timestamp intervals.

    Parameters
    ----------
    df: pandas DataFrame
        APLOSE dataframe with detections
    timestamps: list of int
        unix timestamps

    Returns
    -------

    """
    times_beg = sorted(list(set(x.timestamp() for x in df["start_datetime"])))
    times_end = sorted(list(set(y.timestamp() for y in df["end_datetime"])))

    vec, ranks, k = np.zeros(len(timestamps), dtype=int), [], 0
    for i in range(len(times_beg)):
        for j in range(k, len(timestamps) - 1):
            if int(times_beg[i] * 1e7) in range(
                int(timestamps[j] * 1e7), int(timestamps[j + 1] * 1e7)
            ) or int(times_end[i] * 1e7) in range(
                int(timestamps[j] * 1e7), int(timestamps[j + 1] * 1e7)
            ):
                ranks.append(j)
                k = j
                break
            else:
                continue
    ranks = sorted(list(set(ranks)))
    vec[np.isin(range(len(timestamps)), ranks)] = 1

    return vec


def get_detection_perf(
    df: pd.DataFrame,
    annotators: Iterable,
    annotations: Iterable,
    start: pd.Timestamp = None,
    stop: pd.Timestamp = None,
):
    """Computes the detection performances of a reference annotator in comparison with a second annotator/detector

    Parameters
    ----------
    df: pd.DataFrame
        APLOSE formatted detection/annotation DataFrame
    annotators: Iterable
        list of annotators
    annotations: Iterable
        list of annotations
    start: pd.Timestamp
        begin datetime, optional
    stop: pd.Timestamp
        end datetime, optional
    """
    datetime_begin = df["start_datetime"].min()
    datetime_end = df["start_datetime"].max()
    df_freq = str(df["end_time"].max()) + "s"

    timestamps = [
        ts.timestamp()
        for ts in pd.date_range(start=datetime_begin, end=datetime_end, freq=df_freq)
    ]
    if start and stop:
        if start > stop:
            raise ValueError(
                f"Start timestamp {start} must be smaller than stop timestamp {stop}"
            )
    if start:
        timestamps = [t for t in timestamps if t >= start.timestamp()]
        if not timestamps:
            raise ValueError(f"No annotation superior than start timestamp {start}")
    if stop:
        timestamps = [t for t in timestamps if t <= stop.timestamp()]
        if not timestamps:
            raise ValueError(f"No annotation anterior than stop timestamp {stop}")

    # df1 - REFERENCE
    selected_annotator1 = select_reference(annotators, "annotator")
    selected_label1 = select_reference(annotations)
    selected_annotations1 = df[
        (df["annotator"] == selected_annotator1) & (df["annotation"] == selected_label1)
    ]
    vec1 = _map_datetimes_to_vector(df=selected_annotations1, timestamps=timestamps)

    # df2
    selected_annotator2 = select_reference(
        [annot for annot in annotators if annot != selected_annotator1]
    )
    selected_label2 = select_reference(annotations)
    selected_annotations2 = df[
        (df["annotator"] == selected_annotator2) & (df["annotation"] == selected_label2)
    ]
    vec2 = _map_datetimes_to_vector(selected_annotations2, timestamps)

    # DETECTION PERFORMANCES
    true_pos, false_pos, true_neg, false_neg, error = 0, 0, 0, 0, 0
    for i in range(len(timestamps)):
        if vec1[i] == 0 and vec2[i] == 0:
            true_neg += 1
        elif vec1[i] == 1 and vec2[i] == 1:
            true_pos += 1
        elif vec1[i] == 0 and vec2[i] == 1:
            false_pos += 1
        elif vec1[i] == 1 and vec2[i] == 0:
            false_neg += 1
        else:
            error += 1

    if error != 0:
        raise ValueError(f"Error : {error}")

    print("\n\n### Detection results ###", end="\n")
    print(f"True positive : {true_pos}")
    print(f"True negative : {true_neg}")
    print(f"False positive : {false_pos}")
    print(f"False negative : {false_neg}")

    if true_pos + false_pos == 0 or false_neg + true_pos == 0:
        raise ValueError(f"Precision/Recall computation impossible")

    print(f"\nPRECISION : {true_pos / (true_pos + false_pos):.2f}")
    print(f"RECALL : {true_pos / (false_neg + true_pos):.2f}")

    # f-score : 2*(precision*recall)/(precision+recall)
    f_score = (
        2
        * ((true_pos / (true_pos + false_pos)) * (true_pos / (false_neg + true_pos)))
        / ((true_pos / (true_pos + false_pos)) + (true_pos / (false_neg + true_pos)))
    )
    print(f"F-SCORE : {f_score:.2f}")

    print(
        f"File 1 : {selected_annotator1}/{selected_label1} \nFile 2 : {selected_annotator2}/{selected_label2}"
    )

    return


def _get_resolution_str(bin: int):
    """From a resolution in seconds to corresponding string in day/hour/minute/second resolution

    Parameters
    ----------
    bin: int, in seconds
    """
    if bin // 86400 >= 1:
        bin_str = str(int(bin // 86400)) + "D"
    elif bin // 3600 >= 1:
        bin_str = str(int(bin // 3600)) + "h"
    elif bin // 60 >= 1:
        bin_str = str(int(bin // 60)) + "min"
    else:
        bin_str = str(bin) + "s"

    return bin_str