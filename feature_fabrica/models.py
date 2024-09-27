# models.py
import hashlib
from collections.abc import Callable
from typing import Any, Literal, Optional

import numpy as np
from beartype import beartype
from pydantic import BaseModel, ConfigDict, Field, validator

from feature_fabrica.utils import compute_all_transformations


class FeatureSpec(BaseModel):
    description: str =  Field(min_length=5)
    data_type: str
    group: str  | None = None
    dependencies: list[str] | None = Field(default_factory=list)
    transformation: dict[str, Any] | None = Field(default_factory=dict)

    @validator("data_type")
    def validate_data_type(cls, v):
        try:
            # Check if the data_type is a valid type
            if not (getattr(np, v, None)):
                raise ValueError(
                    f"Invalid data_type specified: {v}, it should be in numpy"
                )
        except Exception as e:
            raise ValueError(f"Invalid data_type: {v}, error: {str(e)}")
        return v

class ArrayLike(np.lib.mixins.NDArrayOperatorsMixin):
    """Mixin class to enable NumPy-like operations for custom models."""

    def _get_value(self):
        raise NotImplementedError()

    def _set_value(self, value: np.ndarray | None):
        raise NotImplementedError()

    def __array__(self, dtype=None, copy=None):
        """Automatic conversion to NumPy array when passed to NumPy functions."""
        if dtype:
            return self._get_value().astype(dtype)
        return self._get_value().copy() if copy else self._get_value()

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        """Handle NumPy universal functions (e.g., np.add, np.multiply)."""
        inputs = tuple(x._get_value() if isinstance(x, ArrayLike) else x for x in inputs)
        result = getattr(ufunc, method)(*inputs, **kwargs)
        return result

    def __array_function__(self, func, types, args, kwargs):
        """Handle array functions like np.mean, np.sum, etc."""
        args = tuple(x._get_value() if isinstance(x, ArrayLike) else x for x in args)
        result = func(*args, **kwargs)
        return result

    def __getitem__(self, idx):
        """Enable indexing like a NumPy array."""
        return self._get_value()[idx]

    def __getattr__(self, name):
        """Enable attribute access for underlying NumPy array properties."""
        return getattr(self._get_value(), name)


class PromiseValue(ArrayLike, BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    value: np.ndarray | None = Field(default=None, exclude=True)
    data_type: str | None = Field(default=None)
    cast: bool = Field(default=True)
    casting: Literal['safe', 'unsafe'] = Field(default="unsafe")
    transformation: Callable | dict[str, Callable] | None = Field(default=None)

    def _get_value(self):
        return self.value

    def _set_value(self, value: np.ndarray | None):
        """Internal method to set value and transform to FeatureValue."""
        if self.data_type is not None:
            self._validate_and_cast_value(value)
        self.value = value

    @beartype
    def __call__(self, data: np.ndarray | None = None):
        if self.transformation is not None:
            result = compute_all_transformations(self.transformation)
            self._set_value(result.value)
        elif data is not None:
            self._set_value(data)
        else:
            raise ValueError("Either transfromation or data should be set!")

    def _validate_and_cast_value(self, value: np.ndarray | None):
        """Validates the value's data type and shape."""
        # Ensure data type is set before validation
        if self.data_type is None:
            raise ValueError("data_type must be specified for validation.")

        # Get the expected data type from numpy
        try:
            expected_dtype = getattr(np, self.data_type)
        except AttributeError:
            raise ValueError(f"Unsupported data type '{self.data_type}', use valid numpy dtype!")

        # Check if the value is a NumPy array
        if not isinstance(value, np.ndarray):
            raise ValueError(f"Value must be a NumPy array, got {type(value).__name__} instead.")

        if value.dtype.type is expected_dtype:
            return

        if self.cast:
            # Validate that the array dtype matches or is compatible with the expected dtype
            if not (np.issubdtype(value.dtype.type, expected_dtype) or np.can_cast(value.dtype.type, expected_dtype, casting=self.casting)):
                raise ValueError(
                    f"Array dtype '{value.dtype}' does not match or is not compatible with expected type '{self.data_type}'"
                )
            value = value.astype(expected_dtype)

    def __repr__(self):
        return f"PromiseValue(value={self._value})"


class TNode(BaseModel):
    """Transformation node for tracking transformation metadata."""
    transformation_name: str
    start_time: float
    end_time: float
    shape: tuple | None = None
    time_taken: float | None = None
    output_hash: str | None = None
    next: Optional["TNode"] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert the node and its next nodes to a dictionary."""
        node_dict = {
            "transformation_name": self.transformation_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "shape": self.shape,
            "time_taken": self.time_taken,
            "output_hash": self.output_hash,
        }
        if self.next:
            node_dict["next"] = self.next.to_dict()
        return node_dict

    def compute_hash(self, data: np.ndarray) -> str:
        """Compute a hash for the output data of the transformation."""
        data_bytes = data.tobytes()
        return hashlib.sha256(data_bytes).hexdigest()

    def store_hash_and_shape(self, output_data: np.ndarray):
        """Store the hash and shape of the output data."""
        self.shape = output_data.shape
        self.output_hash = self.compute_hash(output_data)

    def finalize_metrics(self):
        """Finalize transformation timing metrics."""
        self.time_taken = self.end_time - self.start_time



class THead(BaseModel):
    next: TNode | None = None
