import logging
from pathlib import Path

import numpy as np
import soundfile as sf


def normalize_audio(file: Path, output_folder: Path | None = None) -> None:
    """Normalize the audio data of a file.

    Parameters
    ----------
    file : Path
        The path of the audio file to normalize
    output_folder : Path
        The path to output destination

    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        data, fs = sf.read(file)
    except ValueError as e:
        msg = f"An error occurred while reading file {file}: {e}"
        raise ValueError(msg) from e

    if not output_folder:
        output_folder = file.parent

    format_file = sf.info(file).format
    subtype = sf.info(file).subtype

    data_norm = np.transpose(np.array([data / np.max(np.abs(data))]))[:, 0]

    new_fn = (
        file.stem + ".wav"
        if output_folder != file.parent
        else file.stem + "_normalized.wav"
    )
    new_path = output_folder / new_fn
    sf.write(
        file=new_path,
        data=data_norm,
        samplerate=fs,
        subtype=subtype,
        format=format_file,
    )

    logging.info("File '%s' exported in '%s'", new_fn, file.parent)


def create_raven_file_list(directory: Path) -> None:
    """Create a text file with reference to audio in directory.

    The test file contained the paths of audio files in directory and all subfolders.
    This is useful to open several audio located in different subfolders in Raven.

    Parameters
    ----------
    directory: Path
        Folder containing all audio data

    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # get file list
    files = list(directory.rglob(r"*.wav"))

    # save file list as a txt file
    filename = directory / "Raven_file_list.txt"
    with filename.open(mode="w") as f:
        for item in files:
            f.write(f"{item}\n")

    logging.info("File list saved in '%s'", directory)
