import bisect
import csv
import json
from pathlib import Path

import astral
import easygui
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml
from OSmOSE.config import TIMESTAMP_FORMAT_AUDIO_FILE
from OSmOSE.utils.audio_utils import is_supported_audio_format
from OSmOSE.utils.timestamp_utils import strptime_from_text
from astral.sun import sun
from pandas import date_range, Timestamp, DateOffset
from pandas.tseries.frequencies import to_offset
from scipy.io import wavfile
from scipy.signal import spectrogram


def reshape_timebin(
    df: pd.DataFrame,
    timebin_new: int = None,
    timestamp: list[pd.Timestamp] = None,
) -> pd.DataFrame:
    """
    Reshapes an APLOSE result DataFrame according to a new time bin.

    Parameters
    ----------
    df: pd.DataFrame
        An APLOSE result DataFrame
    timebin_new: int
        The size of the new time bin in seconds
    timestamp: list(pd.Timestamp)
        A list of Timestamp objects

    Returns
    -------
    df_new_timebin: pd.DataFrame
        The reshaped DataFrame

    """
    df = df.sort_values("start_datetime").reset_index(drop=True)
    annotators = df["annotator"].drop_duplicates().to_list()
    labels = df["annotation"].drop_duplicates().to_list()
    max_freq = int(max(df["end_frequency"]))
    tz_data = df["start_datetime"][0].tz

    if not timebin_new:
        timebin_new = get_duration(
            title="Get duration", msg="Enter a new time bin", default="1min"
        )
        frequency = str(timebin_new) + "s"
    else:
        frequency = str(timebin_new) + "s"

    df_new_timebin = pd.DataFrame()
    for annotator in annotators:
        for label in labels:
            df_1annot_1label = df[
                (df["annotator"] == annotator) & (df["annotation"] == label)
            ]

            if len(df_1annot_1label) == 0:
                continue

            if timestamp is not None:
                origin_timebin = (timestamp[1] - timestamp[0]).total_seconds()
                time_vector = [
                    ts.timestamp()
                    for ts in timestamp[0 :: int(timebin_new / origin_timebin)]
                ]
            else:
                t1 = t_rounder(
                    t=df_1annot_1label["start_datetime"].iloc[0], res=timebin_new
                )
                t2 = t_rounder(
                    t=df_1annot_1label["end_datetime"].iloc[-1], res=timebin_new
                )
                time_vector = [
                    ts.timestamp()
                    for ts in pd.date_range(start=t1, end=t2, freq=frequency)
                ]

            ts_detect_beg = [
                ts.timestamp() for ts in df_1annot_1label["start_datetime"]
            ]
            ts_detect_end = [ts.timestamp() for ts in df_1annot_1label["end_datetime"]]

            filenames = df_1annot_1label["filename"]

            filename_vector = []
            for ts in time_vector:
                # insertion of ts in ts_detect_beg, `bisect_left` provides
                # the index of the element in ts_detect_beg that is closest
                # to ts (left element if between 2 elements of the list).
                index = bisect.bisect_left(ts_detect_beg, ts)
                if index == 0:
                    filename_vector.append(filenames.iloc[index])
                else:
                    (
                        filename_vector.append(filenames.iloc[index])
                        if ts in ts_detect_beg
                        else filename_vector.append(filenames.iloc[index - 1])
                    )

            ranks1, ranks2 = [], []
            for i in range(len(df_1annot_1label)):
                idx1 = bisect.bisect_left(time_vector, ts_detect_beg[i])
                idx2 = bisect.bisect_left(time_vector, ts_detect_end[i])
                (
                    ranks1.append(idx1)
                    if ts_detect_beg[i] in time_vector
                    else ranks1.append(idx1 - 1)
                )
                (
                    ranks2.append(idx2)
                    if ts_detect_end[i] in time_vector
                    else ranks2.append(idx2 - 1)
                )

            detect_vec = [0] * len(time_vector)
            for start, end in zip(ranks1, ranks2):
                detect_vec[start : end + 1] = [1] * (end - start + 1)

            start_datetime, end_datetime, filename = [], [], []
            for i in range(len(time_vector)):
                if detect_vec[i] == 1:
                    start_datetime.append(
                        pd.Timestamp(time_vector[i], unit="s", tz=tz_data)
                    )
                    end_datetime.append(
                        pd.Timestamp(time_vector[i] + timebin_new, unit="s", tz=tz_data)
                    )
                    filename.append(filename_vector[i])

            df_1annot_1label_new_timebin = pd.DataFrame()
            df_1annot_1label_new_timebin["dataset"] = [
                df_1annot_1label["dataset"].iloc[0]
            ] * len(start_datetime)
            df_1annot_1label_new_timebin["filename"] = filename
            df_1annot_1label_new_timebin["start_time"] = [0] * len(start_datetime)
            df_1annot_1label_new_timebin["end_time"] = [timebin_new] * len(
                start_datetime
            )
            df_1annot_1label_new_timebin["start_frequency"] = [0] * len(start_datetime)
            df_1annot_1label_new_timebin["end_frequency"] = [max_freq] * len(
                start_datetime
            )
            df_1annot_1label_new_timebin["annotation"] = [label] * len(start_datetime)
            df_1annot_1label_new_timebin["annotator"] = [annotator] * len(
                start_datetime
            )
            df_1annot_1label_new_timebin["start_datetime"] = start_datetime
            df_1annot_1label_new_timebin["end_datetime"] = end_datetime

            df_new_timebin = pd.concat([df_new_timebin, df_1annot_1label_new_timebin])
            df_new_timebin["is_box"] = [0] * len(df_new_timebin)

    return df_new_timebin.sort_values(by=["start_datetime"])


def load_detections(
    file: Path,
    timebin_new: int = None,
    datetime_begin: pd.Timestamp = None,
    datetime_end: pd.Timestamp = None,
    annotator: str = None,
    annotation: str = None,
    box: bool = False,
    timestamp_file: str = None,
    user_sel: str = "all",
    fmin_filter: int = None,
    fmax_filter: int = None,
) -> pd.DataFrame:
    """
    Loads and filters an APLOSE formatted detection file according to user specified filters.

    Parameters
    ----------
    file : Path
        A Path to the detection file
    timebin_new: int
        The new time resolution to set the detections to (in seconds)
    datetime_begin: pd.Timestamp
        A datetime to filter out detections anterior to the datetime
    datetime_end: pd.Timestamp
        A datetime to filter out detections posterior to the datetime
    annotator: str
        A string to filter only detections of a particular annotator
    annotation: str
        A string to filter only detections of a particular annotation
    box: bool, default False
        if True, all annotations are kept, else keeps only absence/presence boxes (weak detection)
    timestamp_file: Path
        A Path to an APLOSE formatted timestamp file.
        It is used to create a reshaped detection file with timestamps that matches the APLOSE annotations.
    user_sel: str, default "all"
        A string to filter detections of a file based on annotators
            'union': the common detections of all annotators and the unique detections of each annotator are selected
            'intersection': only the common detections of all annotators are selected
            'all': all the detections are selected
    fmin_filter: int
        An integer to filter out detections based on a minimum frequency
    fmax_filter: int
        An integer to filter out detections based on a maximum frequency

    Returns
    -------
    result_df: pd.DataFrame
        A DataFrame corresponding to the selected filters and containing all the corresponding detections
    """
    delimiter = find_delimiter(file)

    df = (
        pd.read_csv(file, sep=delimiter, parse_dates=["start_datetime", "end_datetime"])
        .sort_values("start_datetime")
        .reset_index(drop=True)
    )

    df = df.dropna(subset=["annotation"])  # drop lines with only comments

    list_annotators = df["annotator"].drop_duplicates().to_list()
    list_labels = df["annotation"].drop_duplicates().to_list()
    max_freq = int(max(df["end_frequency"]))
    max_time = int(max(df["end_time"]))

    if datetime_begin:
        df = df[df["start_datetime"] >= datetime_begin]
        if len(df) == 0:
            raise Exception(
                f"No detection found after 'datetime_begin' filtering at '{datetime_begin}', upload aborted"
            )

    if datetime_end:
        df = df[df["end_datetime"] <= datetime_end]
        if len(df) == 0:
            raise Exception(
                f"No detection found after 'datetime_end' filtering at '{datetime_end}', upload aborted"
            )

    if annotator:
        if isinstance(annotator, list):
            invalid_annotators = [a for a in annotator if a not in list_annotators]
            if invalid_annotators:
                raise ValueError(
                    f"Annotators {invalid_annotators} are not present in result file annotators, upload aborted"
                )
            df = df.loc[df["annotator"].isin(annotator)]
            list_annotators = annotator
        else:
            if annotator not in list_annotators:
                raise ValueError(
                    f"Annotator '{annotator}' is not present in result file annotators, upload aborted"
                )
            df = df.loc[df["annotator"] == annotator]
            list_annotators = [annotator]

    if annotation:
        if isinstance(annotation, list):
            invalid_annotations = [a for a in annotation if a not in list_labels]
            if invalid_annotations:
                raise ValueError(
                    f"Annotations {invalid_annotations} are not present in result file labels, upload aborted"
                )
            df = df.loc[df["annotation"].isin(annotation)]
        else:
            if annotation not in list_labels:
                raise ValueError(
                    f"Annotation '{annotation}' is not present in result file labels, upload aborted"
                )
            df = df.loc[df["annotation"] == annotation]

    if fmin_filter:
        df = df[df["start_frequency"] >= fmin_filter]
        if len(df) == 0:
            raise Exception(
                f"No detection found after fmin filtering at {fmin_filter}Hz, upload aborted"
            )

    if fmax_filter:
        df = df[df["end_frequency"] <= fmax_filter]
        if len(df) == 0:
            raise Exception(
                f"No detection found after fmax filtering at {fmax_filter}Hz, upload aborted"
            )

    df_no_box = df.loc[
        (df["start_time"] == 0)
        & (df["end_time"] == max_time)
        & (df["end_frequency"] == max_freq)
    ]

    if not box:
        if len(df_no_box) == 0 or timebin_new is not None:
            if timestamp_file:
                timestamp = (
                    pd.read_csv(timestamp_file, parse_dates=["timestamp"])
                    .drop_duplicates()
                    .reset_index(drop=True)["timestamp"]
                )
            else:
                timestamp = None

            df = reshape_timebin(
                df=df,
                timebin_new=timebin_new,
                timestamp=timestamp,
            )
        else:
            df = df_no_box

    if len(list_annotators) > 1 and user_sel in ["union", "intersection"]:
        df = intersection_or_union(df=df, user_sel=user_sel)

    return df.sort_values("start_datetime").reset_index(drop=True)


def intersection_or_union(df: pd.DataFrame, user_sel: str) -> pd.DataFrame:
    """
    Computes the intersection or union of annotations from multiple annotators.

    This function identifies common and differing annotations based on the
    "start_datetime" values in the dataset. The intersection consists of
    annotations that appear in the data for all annotators, while the union
    includes all annotations regardless of overlap.

    Parameters
    ----------
    df : pd.DataFrame
        An APLOSE result DataFrame

    user_sel : str
        Specifies whether to return the "intersection" (annotations shared
        by all annotators) or the "union" (all annotations from all annotators).
        Accepted values are:
        - "intersection": Returns only annotations that appear in all annotators' data.
        - "union": Returns all annotations, including both shared and unique ones.

    Returns
    -------
    pd.DataFrame
        An APLOSE formatted DataFrame containing the selected annotations:
        - If "intersection" is chosen, the output includes only annotations
          present in all annotators' data, with the annotator column merged as "annotator1 ∩ annotator2".
        - If "union" is chosen, the output includes all annotations,
          with the annotator column merged as "annotator1 ∪ annotator2".
    """
    annotators = df["annotator"].drop_duplicates().to_list()
    if not len(annotators) > 1:
        raise ValueError("Not enough annotators detected")

    if user_sel not in ["intersection", "union"]:
        raise ValueError("'user_sel' must be either 'intersection' or 'union'")

    labels = df["annotation"].drop_duplicates().to_list()

    df_inter = pd.DataFrame()
    df_diff = pd.DataFrame()
    for label in labels:
        df_label = df[df["annotation"] == label]
        values = list(df_label["start_datetime"].drop_duplicates())
        common_values = []
        diff_values = []
        error_values = []
        for value in values:
            if df_label["start_datetime"].to_list().count(value) == 2:
                common_values.append(value)
            elif df_label["start_datetime"].to_list().count(value) == 1:
                diff_values.append(value)
            else:
                error_values.append(value)

        df_label_inter = df_label[
            df_label["start_datetime"].isin(common_values)
        ].reset_index(drop=True)
        df_label_inter = df_label_inter.drop_duplicates(subset="start_datetime")
        df_inter = pd.concat([df_inter, df_label_inter]).reset_index(drop=True)

        df_label_diff = df_label[
            df_label["start_datetime"].isin(diff_values)
        ].reset_index(drop=True)
        df_diff = pd.concat([df_diff, df_label_diff]).reset_index(drop=True)

    if user_sel == "intersection":
        df_inter["annotator"] = [" ∩ ".join(annotators)] * len(df_inter)
        return df_inter.sort_values("start_datetime").reset_index(drop=True)
    elif user_sel == "union":
        df_union = pd.concat([df_diff, df_inter]).reset_index(drop=True)
        df_union["annotator"] = [" ∪ ".join(annotators)] * len(df_union)
        return df_union.sort_values("start_datetime").reset_index(drop=True)


def read_yaml(file: Path) -> dict:
    """
    Reads yaml file to extract detection parameters. The extracted parameters
    are then used to import detections using 'sorting_detection'.

    Parameters
    ----------
        file: Path
            A path to the yaml file

    Returns
    -------
        parameters: dict
            Dictionary containing a set of parameters for each csv file
    """
    with open(file, "r", encoding="utf-8") as yaml_file:
        parameters = yaml.safe_load(yaml_file)

    for filename in parameters.keys():
        if not Path(filename).exists():
            raise FileNotFoundError(f"'{filename}' does not exist")
        else:
            parameters[filename]["file"] = Path(filename)

        if parameters[filename]["timebin_new"] and not isinstance(
            parameters[filename]["timebin_new"], int
        ):
            raise ValueError(
                f"An integer must be passed to 'timebin_new', '{parameters[filename]['timebin_new']}' not a valid value."
            )

        if parameters[filename]["fmin_filter"] and not isinstance(
            parameters[filename]["fmin_filter"], int
        ):
            raise ValueError(
                f"An integer must be passed to 'fmin_filter', '{parameters[filename]['fmin_filter']}' not a valid value."
            )

        if parameters[filename]["fmax_filter"] and not isinstance(
            parameters[filename]["fmax_filter"], int
        ):
            raise ValueError(
                f"An integer must be passed to 'fmax_filter', '{parameters[filename]['fmax_filter']}' not a valid value."
            )

        if parameters[filename]["datetime_begin"]:
            try:
                parameters[filename]["datetime_begin"] = pd.Timestamp(
                    parameters[filename]["datetime_begin"]
                )
            except ValueError as e:
                raise ValueError(
                    f"Invalid date format for 'datetime_begin': '{parameters[filename]['datetime_begin']}'"
                ) from e

        if parameters[filename]["datetime_end"]:
            try:
                parameters[filename]["datetime_end"] = pd.Timestamp(
                    parameters[filename]["datetime_end"]
                )
            except ValueError as e:
                raise ValueError(
                    f"Invalid date format for 'datetime_end': {parameters[filename]['datetime_end']}"
                ) from e

        if (
            all(
                [
                    parameters[filename]["datetime_begin"],
                    parameters[filename]["datetime_end"],
                ]
            )
            and parameters[filename]["datetime_begin"]
            >= parameters[filename]["datetime_end"]
        ):
            raise ValueError(
                f'{parameters[filename]["datetime_begin"]} >= {parameters[filename]["datetime_end"]}'
            )

        if parameters[filename]["annotator"] and not (
            isinstance(parameters[filename]["annotator"], str)
            or (
                isinstance(parameters[filename]["annotator"], list)
                and all(
                    isinstance(item, str) for item in parameters[filename]["annotator"]
                )
            )
        ):
            raise ValueError(
                f"A string must be passed to 'annotator', '{parameters[filename]['annotator']}' not a valid value."
            )

        if parameters[filename]["annotation"] and not isinstance(
            parameters[filename]["annotation"], str
        ):
            raise ValueError(
                f"A string must be passed to 'annotation', '{parameters[filename]['annotation']}' not a valid value."
            )

        if parameters[filename]["box"] and not isinstance(
            parameters[filename]["box"], bool
        ):
            raise ValueError(
                f"A boolean must be passed to 'box', '{parameters[filename]['box']}' not a valid value."
            )

        if parameters[filename]["user_sel"] and parameters[filename][
            "user_sel"
        ] not in ["union", "intersection", "all"]:
            raise ValueError(
                f"Either 'union', 'intersection' or 'all' must be passed to 'user_sel', '{parameters[filename]['user_sel']}' not a valid value."
            )

        if parameters[filename]["timestamp_file"]:
            if not Path(parameters[filename]["timestamp_file"]).exists():
                raise FileNotFoundError(
                    f"'{parameters[filename]['timestamp_file']}' does not exist"
                )
            else:
                parameters[filename]["timestamp_file"] = Path(
                    parameters[filename]["timestamp_file"]
                )

    return parameters


def find_delimiter(file: str | Path) -> str:
    """
    Finds the proper delimiter for a csv file.

    Parameters
    ----------
    file: Path
        A Path to a csv file

    Returns
    -------
    delimiter: str
        The delimiter to use to read the file
    """
    with open(file, "r", newline="") as csv_file:
        try:
            temp_lines = csv_file.readline() + "\n" + csv_file.readline()
            dialect = csv.Sniffer().sniff(temp_lines, delimiters=",;")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ","
        return delimiter


def t_rounder(t: pd.Timestamp, res: int):
    """
    Rounds a Timestamp according to the user specified resolution : 10s / 1min / 10 min / 1h / 24h

    Parameters
    ----------
        t: pd.Timestamp
            Datetime to round
        res: integer
            The new resolution in seconds

    Returns
    -------
        t: rounded Timestamp
    """
    if res == 600:  # 10min
        minute = t.minute
        minute = round(minute / 10) * 10
        hour = t.hour
        if minute < 60:
            t = t.replace(minute=minute, second=0, microsecond=0)
        else:
            if hour < 23:
                hour += 1
            else:
                hour = 0
                t += pd.Timedelta(days=1)
                t = t.replace(hour=hour, minute=0, second=0, microsecond=0)
    elif res == 10:  # 10s
        second = t.second
        second = round(second / 10) * 10
        if second < 60:
            t = t.replace(second=second, microsecond=0)
        else:
            t = t + pd.Timedelta(minutes=1)
            t = t.replace(second=0, microsecond=0)
    elif res == 60:  # 1min
        second = round(t.second / 10) * 10
        if second < 60:
            t = t.replace(second=0, microsecond=0)
        else:
            t = t + pd.Timedelta(minutes=1)
            t = t.replace(second=0, microsecond=0)
    elif res == 3600:  # 1h
        t = t.replace(minute=0, second=0, microsecond=0)
    elif res == 86400:  # 24h
        if t > t.replace(hour=12, minute=0, second=0, microsecond=0):
            t = t.replace(hour=0, minute=0, second=0, microsecond=0)
            t += pd.Timedelta(days=1)
        else:
            t = t.replace(hour=0, minute=0, second=0, microsecond=0)
    elif res == 3:
        t = t.replace(microsecond=0)
    elif res > 86400:
        t = t.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"res={res}s: Resolution not available")
    return t


def get_season(ts: pd.Timestamp) -> str:
    """
    Determines the meteorological season for a given timestamp in the Northern Hemisphere.
    Winter is defined as timestamps from December to February, spring from March to May and so on.

    Parameter
    ---------
        ts: pd.Timestamp

    Returns
    -------
        The season and year of ts

    Example
    -------
    get_season(pd.Timestamp("01/01/2023"))
    """
    winter = [1, 2, 12]
    spring = [3, 4, 5]
    summer = [6, 7, 8]
    autumn = [9, 10, 11]

    if ts.month in spring:
        season = "spring" + " " + str(ts.year)
    elif ts.month in summer:
        season = "summer" + " " + str(ts.year)
    elif ts.month in autumn:
        season = "autumn" + " " + str(ts.year)
    elif ts.month in winter and ts.month != 12:
        season = "winter" + " " + str(ts.year - 1)
    elif ts.month in winter and ts.month == 12:
        season = "winter" + " " + str(ts.year)
    else:
        raise ValueError("Invalid timestamp")

    return season


def suntime_hour(start: pd.Timestamp, stop: pd.Timestamp, lat: float, lon: float):
    """
    Fetches sunrise and sunset hours for dates between start and stop.

    Parameters
    ----------
        start: pd.Timestamp
            start datetime of when to fetch sun hour
        stop: pd.Timestamp
            end datetime of when to fetch sun hour
        lat: float
            latitude in decimal degrees
        lon: float
            longitude in decimal degrees

    Returns
    -------
        hour_sunrise: list
            A list of float with sunrise decimal hours for each day between date_beg and date_end
        hour_sunset: list
            A List of float with sunset decimal hours for each day between date_beg and date_end
        dt_dusk: pd.Timestamp
            dusk datetime
        dt_day: pd.Timestamp
            day datetime
        dt_dawn: pd.Timestamp
            dawn datetime
        dt_night: pd.Timestamp
            night datetime
    """
    tz = start.tz

    # localisation info
    gps = astral.LocationInfo(timezone=tz, latitude=lat, longitude=lon)

    # List of days during when the data were recorded
    h_sunrise, h_sunset, dt_dusk, dt_dawn, dt_day, dt_night = [], [], [], [], [], []

    # For each day : find time of sunset, sun rise, begin dawn and dusk
    for date in [
        ts.date() for ts in pd.date_range(start.normalize(), stop.normalize(), freq="D")
    ]:
        # nautical twilight = 12, see def here : https://www.timeanddate.com/astronomy/nautical-twilight.html
        suntime = sun(gps.observer, date=date, dawn_dusk_depression=12)
        dawn, day, _, dusk, night = [
            pd.Timestamp(suntime[period]).tz_convert(tz) for period in suntime
        ]

        for lst, period in zip([h_sunrise, h_sunset], [day, dusk]):
            lst.append(period.hour + period.minute / 60 + period.second / 3600)

        for lst, period in zip(
            [dt_dawn, dt_day, dt_dusk, dt_night], [dawn, day, dusk, night]
        ):
            lst.append(period)

    return h_sunrise, h_sunset, dt_dusk, dt_dawn, dt_day, dt_night


def get_coordinates():
    """
    Asks for user input to get GPS coordinates.

    Returns
    -------
    latitude: float

    longitude: float
    """
    title = "Coordinates in degree° minute'"
    msg = "latitude (N/S) and longitude (E/W)"
    field_names = ["lat decimal degree", "lon decimal degree"]
    field_values = easygui.multenterbox(msg, title, field_names)

    # make sure that none of the fields was left blank
    while True:
        if field_values is None:
            raise TypeError("'get_coordinates()' was cancelled")

        lat, lon = field_values
        errmsg = ""
        try:
            lat_val = float(lat.strip())  # Convert to float for latitude
            if lat_val < -90 or lat_val > 90:
                errmsg += (
                    f"'{lat}' is not a valid latitude. It must be between -90 and 90.\n"
                )
        except ValueError:
            errmsg += f"'{lat}' is not a valid entry for latitude.\n"

        try:
            lon_val = float(lon.strip())  # Convert to float for longitude
            if lon_val < -180 or lon_val > 180:
                errmsg += f"'{lon}' is not a valid longitude. It must be between -180 and 180.\n"
        except ValueError:
            errmsg += f"'{lon}' is not a valid entry for longitude.\n"

        if errmsg == "":
            break

        field_values = easygui.multenterbox(errmsg, title, field_names)

    lat = float(lat.strip())
    lon = float(lon.strip())

    return lat, lon


def get_duration(
    title: str = "Get duration",
    msg: str = "Enter a time alias",
    default: str = "10min",
    base: bool = False,
):
    """
    Asks user input to get time duration.
    Offset aliases are to be used,
    e.g.: '5D' => 432_000s
    '2h' => 7_200s
    '3BMS' => <3*Months>
    See https://pandas.pydata.org/docs/user_guide/timeseries.html#timeseries-offset-aliases

    Parameters
    ----------
    title : str
    msg : str
    default : '10min' => 600s
    base : bool, optional, default False, if True, return the base of the value.
        For instance, "10min" => '<Minute>'

    Returns
    -------
    The total number of seconds of the entered time alias or the time alias if not transposable to duration (<N*Months>)
    """
    value = easygui.enterbox(
        msg=f"{msg}", title=f"{title}", default=f"{default}", strip=True
    )

    while True:
        if value is None:
            raise TypeError("'get_duration()' was cancelled")

        errmsg = ""
        try:
            offset = to_offset(value)
            base_str = offset.base.freqstr
            # Check if the offset is convertible to Timedelta
            try:
                seconds = int(pd.Timedelta(offset).total_seconds())
            except ValueError:
                # For offsets like '3MS', seconds are not defined
                return offset
        except ValueError:
            errmsg = f"'{value}' is not a valid time alias."

        if errmsg == "":
            break

        value = easygui.enterbox(msg=errmsg, title=f"{title}", strip=True)

    if base:
        return seconds, base_str
    else:
        return seconds


def get_datetime_format(
    title: str = "Get datetime format",
    msg: str = "Enter a datetime format code",
    default: str = "%d/%m/%Y\n%H:%M",
) -> str:
    """
    Asks user input to get datetime format.
    Datetime format codes are to be used,
    See https://docs.python.org/fr/3/library/datetime.html

    Parameters
    ----------
    title : str
    msg : str
    default : '%d/%m/%Y\n%H:%M'
    """
    fmt = easygui.enterbox(
        msg=f"{msg}", title=f"{title}", default=f"{default}", strip=True
    )

    while True:
        if fmt is None:
            raise TypeError("'get_duration()' was cancelled")

        errmsg = ""
        datetime_test = pd.Timestamp("now")
        try:
            datetime_test.strftime(format=fmt)
        except ValueError:
            errmsg = f"'{fmt}' is not a valid datetime format code."

        if errmsg == "":
            break

        fmt = easygui.enterbox(msg=errmsg, title=f"{title}", strip=True)

    return fmt


def print_spectro_from_audio(
    file: Path,
    nfft: int = 1024,
    window_size: int = 1024,
    overlap: int = 20,
    ax: bool = True,
):
    """
    Computes and prints a spectrogram from an audio file.

    Parameters
    ----------
    file: Path to the audio file
    nfft
    window_size
    overlap
    ax: bool, show axes based on this value

    Examples
    --------
    audio_file = Path(r"path\to\file")
    print_spectro_from_audio(audio_file)
    """
    if not is_supported_audio_format(file):
        raise ValueError("Audio file format is not supported")

    try:
        sr, data = wavfile.read(file)
    except ValueError as e:
        print(e)

    overlap_samples = int(overlap / 100 * window_size)  # overlap in samples

    frequencies, times, sxx = spectrogram(
        data, fs=sr, nperseg=window_size, noverlap=overlap_samples, nfft=nfft
    )

    my_dpi = 200
    fact_x = 1.3
    fact_y = 1.3
    fig, _ = plt.subplots(
        figsize=(fact_x * 1800 / my_dpi, fact_y * 512 / my_dpi),
        dpi=my_dpi,
    )

    # plt.pcolormesh(times, frequencies, 10 * np.log10(sxx), vmin=20, vmax=100)
    plt.pcolormesh(times, frequencies, 10 * np.log10(sxx))

    if not ax:
        plt.axis("off")
        plt.subplots_adjust(
            top=1, bottom=0, right=1, left=0, hspace=0, wspace=0
        )  # delete white borders
    else:
        plt.tight_layout()

    ech = len(data)
    size_x = (ech - window_size) / overlap_samples
    size_y = nfft / 2
    print(f"X: {size_x:.3f}\nY: {size_y:.3f}")

    return


def print_spectro_from_npz(file: Path, ax: bool = True):
    """
    Computes and prints a spectrogram from a npz file.

    Parameters
    ----------
    file: Path to the npz file
    ax: bool, show axes based on this value

    Examples
    --------
    npz_file = Path(r'path/to/file')
    print_spectro_from_npz(npz_file)
    """
    if not file.suffix == ".npz":
        raise ValueError("NPZ file format must be provided")

    try:
        with np.load(file, allow_pickle=True) as data:
            sxx = data["Sxx"]
            freq = data["Freq"]
            time = data["Time"]
    except ValueError as e:
        print(e)

    my_dpi = 200
    fact_x = 1.3
    fact_y = 1.3
    fig, _ = plt.subplots(
        figsize=(fact_x * 1800 / my_dpi, fact_y * 512 / my_dpi),
        dpi=my_dpi,
    )

    plt.pcolormesh(time, freq, 10 * np.log10(sxx))

    if not ax:
        plt.xticks([], [])
        plt.yticks([], [])
        plt.axis("off")
        plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
    else:
        plt.tight_layout()

    return


def add_weak_detection(
    file: Path, datetime_format: str = TIMESTAMP_FORMAT_AUDIO_FILE
) -> pd.DataFrame:
    """
    Adds weak detection lines to APLOSE formatted DataFrame with only strong detections.

    Parameters
    ----------
    file: Path
        An APLOSE formatted csv file.
    datetime_format: str
        A string corresponding to the datetime format in the `filename` column
    """
    df = load_detections(file=file, box=True)
    annotators = df["annotator"].drop_duplicates().tolist()
    labels = df["annotation"].drop_duplicates().tolist()
    max_freq = int(max(df["end_frequency"]))
    max_time = int(max(df["end_time"]))
    dataset_id = df["dataset"][0]
    tz = df["start_datetime"].iloc[0].tz

    for annotator in annotators:
        for label in labels:
            filenames = (
                df[(df["annotator"] == annotator) & (df["annotation"] == label)][
                    "filename"
                ]
                .drop_duplicates()
                .tolist()
            )
            for f in filenames:
                test = df[(df["filename"] == f) & (df["annotation"] == label)]["is_box"]
                if test.any():
                    start_datetime = strptime_from_text(
                        text=f, datetime_template=datetime_format
                    ).tz_localize(tz)
                    end_datetime = start_datetime + pd.Timedelta(max_time, unit="s")
                    new_line = [
                        dataset_id,
                        f,
                        0,
                        max_time,
                        0,
                        max_freq,
                        label,
                        annotator,
                        start_datetime,
                        end_datetime,
                        0,
                    ]
                    df.loc[len(df.index)] = new_line

    return df.sort_values("start_datetime").reset_index(drop=True)


def json2df(json_path: Path):
    """
    Converts a metadatax json file into a DataFrame

    Parameters
    ----------
    json_path: Path
    """
    with open(json_path, "r", encoding="utf-8") as f:
        df = pd.json_normalize(json.load(f))
        df["deployment_date"] = pd.to_datetime(df["deployment_date"])
        df["recovery_date"] = pd.to_datetime(df["recovery_date"])

    return df


def add_season_period(ax: mpl.axes.Axes = None, bar_height: int = 10):
    """
    Adds a bar at the top of the plot to seasons.

    Parameters
    ----------
    ax: mpl.axes.Axes
        Figure plot

    bar_height: int
        Bar height in pixels
    """
    if not ax:
        ax = plt.gca()

    if not ax.has_data():
        raise ValueError("Axes have no data")

    bins = date_range(
        start=(
            Timestamp(ax.get_xlim()[0], unit="D").normalize() - DateOffset(months=1)
        ).replace(day=1),
        end=(
            Timestamp(ax.get_xlim()[1], unit="D").normalize() + DateOffset(months=1)
        ).replace(day=1),
        freq="MS",
    )

    season_colors = {
        "winter": "#2ce5e3",
        "spring": "#4fcf50",
        "summer": "#ffcf50",
        "autumn": "#fb9a67",
    }

    bin_centers = [
        (bins[i].timestamp() + bins[i + 1].timestamp()) / 2
        for i in range(len(bins) - 1)
    ]
    bin_centers = [Timestamp(center, unit="s") for center in bin_centers]

    bin_seasons = [get_season(bc).split()[0] for bc in bin_centers]
    bar_height = set_bar_height(ax, bar_height)
    bar_bottom = ax.get_ylim()[1] + (0.2 * bar_height)

    for i, season in enumerate(bin_seasons):
        ax.bar(
            bin_centers[i],
            height=bar_height,
            bottom=bar_bottom,
            width=(bins[i + 1] - bins[i]),
            color=season_colors[season],
            align="center",
            zorder=3,
            alpha=0.6,
        )

    plt.ylim(ax.dataLim.ymin, ax.dataLim.ymax)

    return


def set_bar_height(ax: mpl.axes.Axes = None, pixel_height: int = 10):
    """
    Converts pixel height to data coordinates

    Parameters
    ----------
    ax: mpl.axes.Axes

    pixel_height: int
        in pixel
    """
    if not ax:
        ax = plt.gca()

    if not ax.has_data():
        raise ValueError("Axes have no data")

    display_to_data = ax.transData.inverted().transform
    _, data_bottom = display_to_data((0, 0))  # Bottom of the axis
    _, data_top = display_to_data((0, pixel_height))  # Top of the bar

    return data_top - data_bottom  # Convert pixel height to data scale


def add_recording_period(
    df: pd.DataFrame, ax: mpl.axes.Axes = None, bar_height: int = 10
):
    """
    Adds a bar at the bottom on plot to show recording periods.

    Parameters
    ----------
    df: pd.DataFrame
        Includes the recording campaign deployment and recovery dates (typically extracted from metadatax)

    ax: mpl.axes.Axes

    bar_height: int
        Bar height in pixels
    """
    if not ax:
        ax = plt.gca()

    if not ax.has_data():
        raise ValueError("Axes have no data")

    recorder_intervals = [
        (start, end - start)
        for start, end in zip(df["deployment_date"], df["recovery_date"])
    ]

    bar_height = set_bar_height(ax=ax, pixel_height=bar_height)

    ax.broken_barh(
        recorder_intervals,
        (ax.get_ylim()[0] - (1.2 * bar_height), bar_height),
        facecolors="red",
        alpha=0.6,
    )
    plt.ylim(ax.dataLim.ymin, ax.dataLim.ymax)

    return
