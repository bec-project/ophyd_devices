"""Module to represent fields for a PandaBox blocks. 
They can be used to create a schema for the fields of a block.
We use pydantic models to define and validate the representive fields.
#TODO Check reasoneable defaults for the fields from
"""

import enum
from dataclasses import dataclass
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class OP(str, enum.Enum):
    """Operations"""

    READ = "?"
    WRITE = "="


allowed_ops = {"param": [OP.READ, OP.WRITE], "read": [OP.READ], "write": [OP.WRITE]}


class FieldBase(BaseModel):
    """Base class for all field dataclasses.

    Args:
        name (str): The name of the field to be used for the communication with the PandaBox client.
        read (bool, optional): Whether the field is readable. Defaults to False.
        write (bool, optional): Whether the field is writable. Defaults to False.
        multi_value (bool, optional): Whether the field is a multi-value field. Defaults to False.
        sub_type (Literal["param", "read", "write"], optional): The sub-type of the field. Defaults to None.
        info (str, optional): Additional information about the field. Defaults to None.
    """

    name: str
    read: bool
    write: bool
    multi_value: bool
    sub_type: Literal["param", "read", "write"] | None = None
    info: Optional[str] = None

    model_config = ConfigDict(strict=True)


class UIntField(FieldBase):
    """Dataclass for unsigned integer fields.

    Args:
        max_value (int, optional): The maximum value of the field. Defaults to None.
    """

    value: int = Field(ge=0)
    max_value: int = Field(ge=0)


class IntField(FieldBase):
    """Dataclass for signed integer fields."""


class ScalarField(FieldBase):
    """Dataclass for scalar fields.

    Args:
        raw (int): The raw value of the field.
        scale (float, optional): The scale factor of the field.
        offset (float, optional): The offset of the field.
        units (str, optional): The units of the field.
    """

    raw: int
    scale: float
    offset: float
    units: str


class BitField(FieldBase):
    """Dataclass representing the FPGA bit fields."""


class ActionField(FieldBase):
    """Dataclass representing an action field.
    This can only be written to, and is used to trigger an action in the FPGA.
    """

    value: str = ""


class LutField(FieldBase):
    """Dataclass representing the FPGA look-up table fields.
    Used in the LUT blocks to implement logic functions, i.e AND, OR, etc.
    Check https://pandablocks.github.io/PandABlocks-server/master/fields.html for more details.

    Args:
        raw (str): The raw value of the field.
    """

    raw: str


class EnumField(FieldBase):
    """Enum field, representing the possible values for a field."""

    values: List[str]


class TimeField(FieldBase):
    """Time field, representing a time value."""

    raw: int
    units: Literal["s", "ms", "us", "ns"]


class BitOutField(FieldBase):
    """Dataclass represeting the BITOUT fields.

    Args:
        capture_word (str): This specifies which bit can be used to capture the output of this field, i.e. for the PCAP block.
        offset (int): The bit offset to from the bit specified in capture_word.
    """

    capture_word: Optional[str]
    offset: Optional[int]


class BitMuxField(FieldBase):
    """Dataclass representing the BITMUX fields.

    Args:
        value (Literal["ONE", "ZERO"] | BitOutField): The value of the field, either "ONE", "ZERO" or a BitOutField.
        delay (int, optional): The delay of accepting the signal of this field. Defaults to None.
        max_delay (int, optional): The maximum delay of the field. Defaults to None.
    """

    value: Literal["ONE", "ZERO"] | BitOutField
    delay: Optional[int]
    max_delay: Optional[int]


PANDA_FIELDS = {
    "uint": UIntField,
    "int": IntField,
    "scalar": ScalarField,
    "bit": BitField,
    "action": ActionField,
    "lut": LutField,
    "enum": EnumField,
    "time": TimeField,
    "bit_out": BitOutField,
    "bit_mux": BitMuxField,
}


# TODO to be checked these blocks
# class PosOutField(FieldBase):
#     capture: Optional[bool] = False
#     offset: Optional[int] = None
#     scale: Optional[float] = None
#     units: Optional[str] = None
#     scaled: Optional[float] = None


# @dataclass
# class ExtOutField(FieldBase):
#     bits: Optional[List[int]] = None


# @dataclass
# class TableField(FieldBase):
#     max_length: Optional[int] = None
#     length: Optional[int] = None
#     base64_data: Optional[str] = None
#     fields: Optional[str] = None
#     row_words: Optional[int] = None
