"""Methods for managing and validating filenames and filepaths."""
# ruff: noqa: PLR0913

from __future__ import annotations

import re
from abc import abstractmethod
from datetime import datetime
from pathlib import Path

import imap_data_access


def generate_imap_file_path(filename: str) -> ImapFilePath:
    """Generate an ImapFilePath object from a filename.

    This method determines if the filename is a SPICE, Science, or Ancillary file and
    returns a SPICEFilePath, ScienceFilePath, or AncillaryFilePath object respectively.

    Parameters
    ----------
    filename : str
        The filename to generate a path for.

    Returns
    -------
    A FilePath object
    """
    try:
        # SPICE
        path_obj = imap_data_access.SPICEFilePath(filename)
    except SPICEFilePath.InvalidSPICEFileError:
        # Science and Ancillary
        try:
            path_obj = imap_data_access.ScienceFilePath(filename)
        except ScienceFilePath.InvalidScienceFileError:
            # If Science file fails, then process as an Ancillary file
            try:
                path_obj = imap_data_access.AncillaryFilePath(filename)
            except AncillaryFilePath.InvalidAncillaryFileError as e:
                # Matches neither file format
                error_message = (
                    f"Invalid file type for {filename}. It does not match"
                    f"Spice, Science or Ancillary file formats"
                )
                raise ValueError(error_message) from e

    return path_obj


class ImapFilePath:
    """Base class for FilePaths.

    Includes shared static methods and provides correct typing for ScienceFilePath,
    AncillaryFilePath, and SPICEFilePath.
    """

    @staticmethod
    def is_valid_date(input_date: str) -> bool:
        """Check input date string is in valid format and is correct date.

        Parameters
        ----------
        input_date : str
            Date in YYYYMMDD format.

        Returns
        -------
        bool
            Whether date input is valid or not
        """
        # Validate if it's a real date
        try:
            # This checks if date is in YYYYMMDD format.
            # Sometimes, date is correct but not in the format we want
            datetime.strptime(input_date, "%Y%m%d")
            return True
        except ValueError:
            return False

    @staticmethod
    def is_valid_version(input_version: str) -> bool:
        """Check input version string is in valid format 'vXXX' or 'latest'.

        Parameters
        ----------
        input_version : str
            Version to be checked.

        Returns
        -------
        bool
            Whether input version is valid or not.
        """
        return input_version == "latest" or re.fullmatch(r"v\d{3}", input_version)

    @abstractmethod
    def construct_path(self) -> Path:
        """Construct valid path from class variables and data_dir."""
        raise NotImplementedError


class ScienceFilePath(ImapFilePath):
    """Class for building and validating filepaths for science files."""

    class InvalidScienceFileError(Exception):
        """Indicates a bad file type."""

        pass

    def __init__(self, filename: str | Path):
        """Class to store filepath and file management methods for science files.

        If you have an instance of this class, you can be confident you have a valid
        science file and generate paths in the correct format. The parent of the file
        path is set by the "IMAP_DATA_DIR" environment variable, or defaults to "data/"

        Current filename convention:
        <mission>_<instrument>_<datalevel>_<descriptor>_<start_date>(-<repointing>)
        _<version>.<extension>

        NOTE: There are no optional parameters. All parameters are required.
        <mission>: imap
        <instrument>: codice, glows, hi, hit, idex, lo, mag, swapi, swe, ultra
        <data_level> : l1a, l1b, l1, l3a and etc.
        <descriptor>: descriptor stores information specific to instrument. This is
            decided by each instrument. For L0, "raw" is used.
        <start_date>: startdate is the earliest date in the data, format: YYYYMMDD
        <repointing>: This is an optional field. It is used to indicate which
            repointing the data is from, format: repointXXXXX
        <version>: This stores the data version for this product, format: vXXX

        Parameters
        ----------
        filename : str | Path
            Science data filename or file path.
        """
        self.filename = Path(filename)
        self.data_dir = imap_data_access.config["DATA_DIR"]

        try:
            split_filename = self.extract_filename_components(self.filename)
        except ValueError as err:
            raise self.InvalidScienceFileError(
                f"Invalid filename. Expected file to match format: "
                f"{imap_data_access.FILENAME_CONVENTION}"
            ) from err

        self.mission = split_filename["mission"]
        self.instrument = split_filename["instrument"]
        self.data_level = split_filename["data_level"]
        self.descriptor = split_filename["descriptor"]
        self.start_date = split_filename["start_date"]
        self.repointing = split_filename["repointing"]
        self.version = split_filename["version"]
        self.extension = split_filename["extension"]

        self.error_message = self.validate_filename()
        if self.error_message:
            raise self.InvalidScienceFileError(f"{self.error_message}")

    @classmethod
    def generate_from_inputs(
        cls,
        instrument: str,
        data_level: str,
        descriptor: str,
        start_time: str,
        version: str,
        repointing: int | None = None,
    ) -> ScienceFilePath:
        """Generate a filename from given inputs and return a ScienceFilePath instance.

        This can be used instead of the __init__ method to make a new instance:
        ```
        science_file_path = ScienceFilePath.generate_from_inputs("mag", "l0", "test",
            "20240213", "v001")
        full_path = science_file_path.construct_path()
        ```

        Parameters
        ----------
        descriptor : str
            The descriptor for the filename
        instrument : str
            The instrument for the filename
        data_level : str
            The data level for the filename
        start_time: str
            The start time for the filename
        version : str
            The version of the data
        repointing : int, optional
            The repointing number for this file, optional field that
            is not always present

        Returns
        -------
        str
            The generated filename
        """
        extension = "cdf"
        if data_level == "l0":
            extension = "pkts"
        time_field = start_time
        if repointing:
            time_field += f"-repoint{repointing:05d}"
        filename = (
            f"imap_{instrument}_{data_level}_{descriptor}_{time_field}_"
            f"{version}.{extension}"
        )
        return cls(filename)

    def validate_filename(self) -> str:
        """Validate the filename and populate the error message for wrong attributes.

        The error message will be an empty string if the filename is valid. Otherwise,
        all errors with the filename will be put into the error message.

        Returns
        -------
        error_message: str
            Error message for specific missing attribute, or "" if the file name is
            valid.
        """
        error_message = ""

        if any(
            attr is None or attr == ""
            for attr in [
                self.mission,
                self.instrument,
                self.data_level,
                self.descriptor,
                self.start_date,
                self.version,
                self.extension,
            ]
        ):
            error_message = (
                f"Invalid filename, missing attribute. Filename "
                f"convention is {imap_data_access.FILENAME_CONVENTION} \n"
            )
        if self.mission != "imap":
            error_message += f"Invalid mission {self.mission}. Please use imap \n"

        if self.instrument not in imap_data_access.VALID_INSTRUMENTS:
            error_message += (
                f"Invalid instrument {self.instrument}. Please choose "
                f"from "
                f"{imap_data_access.VALID_INSTRUMENTS} \n"
            )
        if self.data_level not in imap_data_access.VALID_DATALEVELS:
            error_message += (
                f"Invalid data level {self.data_level}. Please choose "
                f"from "
                f"{imap_data_access.VALID_DATALEVELS} \n"
            )
        if not self.is_valid_date(self.start_date):
            error_message += "Invalid start date format. Please use YYYYMMDD format. \n"
        if not bool(re.match(r"^v\d{3}$", self.version)):
            error_message += "Invalid version format. Please use vXXX format. \n"
        if self.repointing and not isinstance(self.repointing, int):
            error_message += "The repointing number should be an integer.\n"

        if self.extension not in imap_data_access.VALID_FILE_EXTENSION or (
            (self.data_level == "l0" and self.extension != "pkts")
            or (self.data_level != "l0" and self.extension != "cdf")
        ):
            error_message += (
                "Invalid extension. Extension should be pkts for data "
                "level l0 and cdf for data level higher than l0 \n"
            )

        return error_message

    def construct_path(self) -> Path:
        """Construct valid path from class variables and data_dir.

        If data_dir is not None, it is prepended on the returned path.

        expected return:
        <data_dir>/mission/instrument/data_level/startdate_month/startdate_day/filename

        Returns
        -------
        Path
            Upload path
        """
        upload_path = Path(
            f"{self.mission}/{self.instrument}/{self.data_level}/"
            f"{self.start_date[:4]}/{self.start_date[4:6]}/{self.filename}"
        )
        if self.data_dir:
            upload_path = self.data_dir / upload_path

        return upload_path

    @staticmethod
    def extract_filename_components(filename: str | Path) -> dict:
        """Extract all components from filename. Does not validate instrument or level.

        Will return a dictionary with the following keys:
        { instrument, datalevel, descriptor, startdate, enddate, version, extension }

        If a match is not found, a ValueError will be raised.

        Generally, this method should not be used directly. Instead the class should
        be used to make a `ScienceFilepath` object.

        Parameters
        ----------
        filename : Path or str
            Path of dependency data.

        Returns
        -------
        components : dict
            Dictionary containing components.
        """
        pattern = (
            r"^(?P<mission>imap)_"
            r"(?P<instrument>[^_]+)_"
            r"(?P<data_level>[^_]+)_"
            r"(?P<descriptor>[^_]+)_"
            r"(?P<start_date>\d{8})"
            r"(-repoint(?P<repointing>\d{5}))?"  # Optional repointing field
            r"_(?P<version>v\d{3})"
            r"\.(?P<extension>cdf|pkts)$"
        )
        if isinstance(filename, Path):
            filename = filename.name

        match = re.match(pattern, filename)
        if match is None:
            raise ScienceFilePath.InvalidScienceFileError(
                f"Filename {filename} does not match expected pattern: "
                f"{imap_data_access.FILENAME_CONVENTION}"
            )

        components = match.groupdict()
        if components["repointing"]:
            # We want the repointing number as an integer
            components["repointing"] = int(components["repointing"])
        return components

    @staticmethod
    def is_valid_repointing(input_repointing: str) -> bool:
        """Check input repointing string is in valid format 'repointingXXXXX'.

        Parameters
        ----------
        input_repointing : str
            Repointing to be checked.

        Returns
        -------
        bool
            Whether input repointing is valid or not.
        """
        return re.fullmatch(r"repoint\d{5}", str(input_repointing))


# Transform the suffix to the directory structure we are using
# Commented out mappings are not being used on IMAP
_SPICE_DIR_MAPPING = {
    ".bc": "ck",
    # ".bds": "dsk",
    # ".bes": "ek",
    ".bpc": "pck",
    ".bsp": "spk",
    ".mk": "mk",
    ".repoint.csv": "repoint",
    ".sff": "activities",
    ".spin.csv": "spin",
    ".tf": "fk",
    # "ti": "ik",
    ".tls": "lsk",
    ".tm": "mk",
    ".tpc": "pck",
    ".tsc": "sclk",
}
"""These are the valid extensions for SPICE files according to NAIF
https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/kernel.html

.bc    binary CK
.bds   binary DSK
.bes   binary Sequence Component EK
.bpc   binary PCK
.bsp   binary SPK
.tf    text FK
.ti    text IK
.tls   text LSK
.tm    text meta-kernel (FURNSH kernel)
.tpc   text PCK
.tsc   text SCLK
"""


class SPICEFilePath(ImapFilePath):
    """Class for building and validating filepaths for SPICE files."""

    class InvalidSPICEFileError(Exception):
        """Indicates a bad file type."""

        pass

    def __init__(self, filename: str | Path):
        """Class to store filepath and file management methods for SPICE files.

        If you have an instance of this class, you can be confident you have a valid
        SPICE file and generate paths in the correct format. The parent of the file
        path is set by the "IMAP_DATA_DIR" environment variable, or defaults to "data/"

        IMAP_DATA_DIR/spice/<subdir>/filename"

        Parameters
        ----------
        filename : str | Path
            SPICE data filename or file path.
        """
        self.filename = Path(filename)
        if self.filename.suffix == ".csv":
            all_suffixes = self.filename.suffixes  # Returns ['.spin', '.csv']
            self.file_extension = "".join(all_suffixes)  # Returns '.spin.csv'
        else:
            self.file_extension = self.filename.suffix

        if self.file_extension not in _SPICE_DIR_MAPPING:
            raise self.InvalidSPICEFileError(
                f"Invalid SPICE file. Expected file to have one of the following "
                f"extensions {list(_SPICE_DIR_MAPPING.keys())}"
            )

    def construct_path(self) -> Path:
        """Construct valid path from the class variables and data_dir.

        expected return:
        <data_dir>/imap/spice/<subdir>/filename

        Returns
        -------
        Path
            Upload path
        """
        spice_dir = imap_data_access.config["DATA_DIR"] / "spice"
        subdir = _SPICE_DIR_MAPPING[self.file_extension]
        # Use the file suffix to determine the directory structure
        # IMAP_DATA_DIR/spice/<subdir>/filename
        return spice_dir / subdir / self.filename


class AncillaryFilePath(ImapFilePath):
    """Class for building and validating filepaths for Ancillary files."""

    class InvalidAncillaryFileError(Exception):
        """Indicates a bad file type."""

        pass

    def __init__(self, filename: str | Path):
        """Class to store filepath and file management methods for Ancillary files.

        If you have an instance of this class, you can be confident you have a valid
        ancillary file and generate paths in the correct format. The parent of the file
        path is set by the "IMAP_DATA_DIR" environment variable, or defaults to "data/"

        Current filename convention:
        "<mission>_<instrument>_<descriptor>_<start_date>(-<end_date>)_
        <version>.<extension>"

        <mission>: imap
        <instrument>: codice, glows, hi, hit, idex, lo, mag, swapi, swe, ultra
        <descriptor>: A descriptive name for the ancillary file which
                       distinguishes between other ancillary files used by the
                       instrument.
        <start_date>: startdate is the earliest date where the file is valid,
                     format: YYYYMMDD
        <end_date>: The end time of the validity of the ancillary file,
                    in the format “YYYYMMDD”. This is optional for files, with the
                    understanding that if end_date is not provided, the file is valid
                    until a file with a later start_date and no end_date.
        <version>: This stores the data version for this product, format: vXXX

        Parameters
        ----------
        filename : str | Path
            Ancillary data filename or file path.
        """
        self.filename = Path(filename)
        self.data_dir = imap_data_access.config["DATA_DIR"]

        try:
            split_filename = self.extract_filename_components(self.filename)
        except ValueError as err:
            raise self.InvalidAncillaryFileError(
                f"Invalid filename. Expected file to match format: "
                f"{imap_data_access.ANCILLARY_FILENAME_CONVENTION}"
            ) from err

        self.mission = split_filename["mission"]
        self.instrument = split_filename["instrument"]
        self.descriptor = split_filename["descriptor"]
        self.start_date = split_filename["start_date"]
        self.end_date = split_filename["end_date"]
        self.version = split_filename["version"]
        self.extension = split_filename["extension"]

        self.error_message = self.validate_filename()
        if self.error_message:
            raise self.InvalidAncillaryFileError(f"{self.error_message}")

    @classmethod
    def generate_from_inputs(
        cls,
        instrument: str,
        descriptor: str,
        version: str,
        extension: str,
        start_time: str,
        end_time: str | None = None,
    ) -> AncillaryFilePath:
        """Generate filename from given inputs and return a AncillaryFilePath instance.

        This can be used instead of the __init__ method to make a new instance:
        ```
        ancillary_file_path = AncillaryFilePath.generate_from_inputs("mag",
        "mag-rotation-matrices", "20240213", "v001")
        full_path = ancillary_file_path.construct_path()
        ```

        Parameters
        ----------
        instrument : str
            The instrument for the filename.
        descriptor : str
            The descriptor for the ancillary filename.
        version : str
            The version of the data.
        extension : str
            The extension type of the file.
        start_time: str
            The start time for the filename. An updated
            start time or the mission start time.
        end_time: str, optional
            The end time for the filename. If not provided,
            the file is valid until a file with a later
            start_date and no end_date.

        Returns
        -------
        str
            The generated filename
        """
        if end_time:
            filename = (
                f"imap_{instrument}_{descriptor}_{start_time}-{end_time}_"
                f"{version}.{extension}"
            )
        else:
            filename = (
                f"imap_{instrument}_{descriptor}_{start_time}_{version}.{extension}"
            )
        return cls(filename)

    def validate_filename(self) -> str:
        """Validate the filename and populate the error message for wrong attributes.

        The error message will be an empty string if the filename is valid. Otherwise,
        all errors with the filename will be put into the error message.

        Returns
        -------
        error_message: str
            Error message for specific missing attribute, or "" if the file name is
            valid.
        """
        error_message = ""

        if any(
            attr is None or attr == ""
            for attr in [
                self.mission,
                self.instrument,
                self.descriptor,
                self.version,
                self.extension,
            ]
        ):
            error_message = (
                f"Invalid filename, missing attribute. Filename "
                f"convention is {imap_data_access.ANCILLARY_FILENAME_CONVENTION} \n"
            )
        if self.mission != "imap":
            error_message += f"Invalid mission {self.mission}. Please use imap \n"

        if self.instrument not in imap_data_access.VALID_INSTRUMENTS:
            error_message += (
                f"Invalid instrument {self.instrument}. Please choose from "
                f"{imap_data_access.VALID_INSTRUMENTS} \n"
            )

        if self.extension not in imap_data_access.VALID_ANCILLARY_FILE_EXTENSION:
            error_message += (
                "Invalid extension. Extension should be cdf. \n"  # TODO: Change this
            )

        if not ScienceFilePath.is_valid_date(self.start_date):
            error_message += "Invalid start date format. Please use YYYYMMDD format. \n"

        if self.end_date:
            if not ScienceFilePath.is_valid_date(self.end_date):
                error_message += (
                    "Invalid end date format. Please use YYYYMMDD format. \n"
                )

        return error_message

    def construct_path(self) -> Path:
        """Construct valid path from class variables and data_dir.

        If data_dir is not None, it is prepended on the returned path.

        expected return:
        <data_dir>/mission/instrument/filename

        Returns
        -------
        Path
            Upload path
        """
        upload_path = Path(
            f"{self.mission}/ancillary/{self.instrument}/{self.filename}"
        )
        if self.data_dir:
            upload_path = self.data_dir / upload_path

        return upload_path

    @staticmethod
    def extract_filename_components(filename: str | Path) -> dict:
        """Extract all components from filename. Does not validate instrument or level.

        Will return a dictionary with the following keys:
        { instrument, descriptor, start_date, end_date, version, extension }

        If a match is not found, a ValueError will be raised.

        Generally, this method should not be used directly. Instead the class should
        be used to make a `AncillaryFilepath` object.

        Parameters
        ----------
        filename : Path or str
            Path of dependency data.

        Returns
        -------
        components : dict
            Dictionary containing components.
        """
        pattern = (
            r"^(?P<mission>imap)_"
            r"(?P<instrument>[^_]+)_"
            r"(?P<descriptor>[^_]+)_"
            r"(?P<start_date>\d{8})"
            r"(-(?P<end_date>\d{8}))?"  # Optional end_date field
            r"_(?P<version>v\d{3})"
            r"\.(?P<extension>cdf|cvs|json)$"
        )
        if isinstance(filename, Path):
            filename = filename.name

        match = re.match(pattern, filename)
        if match is None:
            raise AncillaryFilePath.InvalidAncillaryFileError(
                f"Filename {filename} does not match expected pattern: "
                f"{imap_data_access.ANCILLARY_FILENAME_CONVENTION}"
            )

        components = match.groupdict()
        return components
