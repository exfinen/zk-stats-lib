from abc import abstractmethod
from typing import Callable, Type, Optional, Union

import torch
from torch import nn
import json

from .ops import (
    Operation,
    Mean,
    Median,
    GeometricMean,
    HarmonicMean,
    Mode,
    PStdev,
    PVariance,
    Stdev,
    Variance,
    Covariance,
    Correlation,
    Regression,
    Where,
    IsResultPrecise,
)


DEFAULT_ERROR = 0.01


class State:
    """
    State is a container for intermediate results of computation.

    Stage 1 (current_op_index is None): for every call to State (mean, median, etc.), result
        is calculated and temporarily stored in the state. Call `set_ready_for_exporting_onnx` to indicate
    Stage 2: all operations are calculated and results are ready to be used. Call `set_ready_for_exporting_onnx`
        to indicate it's ready to generate settings.
    Stage 3 (current_op_index is not None): when exporting to onnx, when the operations are called, the results and
        the conditions are popped from the state and filled in the onnx graph.
    """
    def __init__(self, error: float) -> None:
        self.ops: list[Operation] = []
        self.bools: list[Callable[[], torch.Tensor]] = []
        self.error: float = error
        # Pointer to the current operation index. If None, it's in stage 1. If not None, it's in stage 3.
        self.current_op_index: Optional[int] = None
        self.precal_witness_path: str = None
        self.precal_witness:dict = {}
        self.isProver:bool = None

    def set_ready_for_exporting_onnx(self) -> None:
        self.current_op_index = 0
    # def set_witness(self,witness_array) -> None:
    #     self.witness_array = witness_array
    # def set_aggregate_witness_path(self,aggregate_witness_path) -> None:
    #     self.aggregate_witness_path = aggregate_witness_path
    # def get_aggregate_witness(self) -> list[torch.Tensor]:
    #     return self.aggregate_witness
    def mean(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate the mean of the input tensor. The behavior should conform to
        [statistics.mean](https://docs.python.org/3/library/statistics.html#statistics.mean) in Python standard library.
        """
        return self._call_op([x], Mean)

    def median(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate the median of the input tensor. The behavior should conform to
        [statistics.median](https://docs.python.org/3/library/statistics.html#statistics.median) in Python standard library.
        """
        return self._call_op([x], Median)

    def geometric_mean(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate the geometric mean of the input tensor. The behavior should conform to
        [statistics.geometric_mean](https://docs.python.org/3/library/statistics.html#statistics.geometric_mean) in Python standard library.
        """
        return self._call_op([x], GeometricMean)

    def harmonic_mean(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate the harmonic mean of the input tensor. The behavior should conform to
        [statistics.harmonic_mean](https://docs.python.org/3/library/statistics.html#statistics.harmonic_mean) in Python standard library.
        """
        return self._call_op([x], HarmonicMean)

    def mode(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate the mode of the input tensor. The behavior should conform to
        [statistics.mode](https://docs.python.org/3/library/statistics.html#statistics.mode) in Python standard library.
        """
        return self._call_op([x], Mode)

    def pstdev(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate the population standard deviation of the input tensor. The behavior should conform to
        [statistics.pstdev](https://docs.python.org/3/library/statistics.html#statistics.pstdev) in Python standard library.
        """
        return self._call_op([x], PStdev)

    def pvariance(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate the population variance of the input tensor. The behavior should conform to
        [statistics.pvariance](https://docs.python.org/3/library/statistics.html#statistics.pvariance) in Python standard library.
        """
        return self._call_op([x], PVariance)

    def stdev(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate the sample standard deviation of the input tensor. The behavior should conform to
        [statistics.stdev](https://docs.python.org/3/library/statistics.html#statistics.stdev) in Python standard library.
        """
        return self._call_op([x], Stdev)

    def variance(self, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate the sample variance of the input tensor. The behavior should conform to
        [statistics.variance](https://docs.python.org/3/library/statistics.html#statistics.variance) in Python standard library.
        """
        return self._call_op([x], Variance)

    def covariance(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        """
        Calculate the covariance of x and y. The behavior should conform to
        [statistics.covariance](https://docs.python.org/3/library/statistics.html#statistics.covariance) in Python standard library.
        """
        return self._call_op([x, y], Covariance)

    def correlation(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        """
        Calculate the correlation of x and y. The behavior should conform to
        [statistics.correlation](https://docs.python.org/3/library/statistics.html#statistics.correlation) in Python standard library.
        """
        return self._call_op([x, y], Correlation)

    def linear_regression(self, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        """
        Calculate the linear regression of x and y. The behavior should conform to
        [statistics.linear_regression](https://docs.python.org/3/library/statistics.html#statistics.linear_regression) in Python standard library.
        """
        # hence support only one x for now
        return self._call_op([x, y], Regression)

    # WHERE operation
    def where(self, filter: torch.Tensor, x: torch.Tensor) -> torch.Tensor:
        """
        Calculate the where operation of x. The behavior should conform to `torch.where` in PyTorch.

        :param filter: A boolean tensor serves as a filter
        :param x: A tensor to be filtered
        :return: filtered tensor
        """
        return self._call_op([filter, x], Where)

    def _call_op(self, x: list[torch.Tensor], op_type: Type[Operation]) -> Union[torch.Tensor, tuple[IsResultPrecise, torch.Tensor]]:
        if self.current_op_index is None:
            # for prover
            if self.isProver:
                print('Prover side')
                op = op_type.create(x, self.error)
                # print('oppy : ', op)
                # print('is check pri 1: ', isinstance(op,Mean))
                if isinstance(op,Mean):
                    self.precal_witness['Mean'] = [op.result.data.item()]
            # for verifier
            else:
                print('Verifier side')
                # if isinstance(op,Mean):
                precal_witness = json.loads(open(self.precal_witness_path, "r").read())
                # tensor_arr = []
                # for ele in data:
                #     tensor_arr.append(torch.tensor(ele))
                op = op_type.create(x, self.error, precal_witness)   
            self.ops.append(op)
            return op.result
        else:
            # Copy the current op index to a local variable since self.current_op_index will be incremented.
            current_op_index = self.current_op_index
            # Sanity check that current op index is not out of bound
            len_ops = len(self.ops)
            if current_op_index >= len(self.ops):
                raise Exception(f"current_op_index out of bound: {current_op_index=} >= {len_ops=}")

            op = self.ops[current_op_index]
            # Sanity check that the operation type matches the current op type
            if not isinstance(op, op_type):
                raise Exception(f"operation type mismatch: {op_type=} != {type(op)=}")

            # Increment the current op index
            self.current_op_index += 1

            # Push the ezkl condition, which is checked only in the last operation
            def is_precise() -> IsResultPrecise:
                return op.ezkl(x)
            self.bools.append(is_precise)
            
            # self.x.append(x)

            # If this is the last operation, aggregate all `is_precise` in `self.bools`, and return (is_precise_aggregated, result)
            # else, return only result
            # print('all ops:', self.ops)
            if current_op_index == len_ops - 1:
                print('final op: ', op)
                # Sanity check for length of self.ops and self.bools
                len_bools = len(self.bools)
                if len_ops != len_bools:
                    raise Exception(f"length mismatch: {len_ops=} != {len_bools=}")
                is_precise_aggregated = torch.tensor(1.0)
                for i in range(len_bools):
                    res = self.bools[i]()
                    # print("hey computation: ", i)
                    # print('self.ops: ', self.ops[i])
                    # print('res: ', res)
                    is_precise_aggregated = torch.logical_and(is_precise_aggregated, res)
                if isinstance(op, Where):
                    # return as where result
                    return is_precise_aggregated, op.result+x[1]-x[1]
                else:
                    if self.isProver:
                        json.dump(self.precal_witness, open(self.precal_witness_path, 'w'))
                    return is_precise_aggregated, op.result+(x[0]-x[0])[0][0][0]

            elif current_op_index > len_ops - 1:
                # Sanity check that current op index does not exceed the length of ops
                raise Exception(f"current_op_index out of bound: {current_op_index=} > {len_ops=}")
            else:
                # for where
                if isinstance(op, Where):
                    return (op.result+x[1]-x[1])
                else: 
                    # return single float number
                    # return torch.where(x[0], x[1], 9999999)
                    # print('oppy else: ', op)
                    # print('is check else: ', isinstance(op,Mean))
                    # self.aggregate_witness.append(op.result)
                    return op.result+(x[0]-x[0])[0][0][0]


class IModel(nn.Module):
    @abstractmethod
    def preprocess(self, x: list[torch.Tensor]) -> None:
        ...

    @abstractmethod
    def forward(self, *x: list[torch.Tensor]) -> tuple[IsResultPrecise, torch.Tensor]:
        ...


# An computation function. Example:
# def computation(state: State, x: list[torch.Tensor]):
#     out_0 = state.median(x[0])
#     out_1 = state.median(x[1])
#     return state.mean(torch.tensor([out_0, out_1]).reshape(1,-1,1))
TComputation = Callable[[State, list[torch.Tensor]], torch.Tensor]


def computation_to_model(computation: TComputation, precal_witness_path:str, isProver:bool ,error: float = DEFAULT_ERROR ) -> tuple[State, Type[IModel]]:
    """
    Create a torch model from a `computation` function defined by user
    :param computation: A function that takes a State and a list of torch.Tensor, and returns a torch.Tensor
    :param error: The error tolerance for the computation.
    :return: A tuple of State and Model. The Model is a torch model that can be used for exporting to onnx.
    State is a container for intermediate results of computation, which can be useful when debugging.
    """
    state = State(error)
    # if it's verifier
    
    state.precal_witness_path= precal_witness_path
    state.isProver = isProver

    class Model(IModel):
        def preprocess(self, x: list[torch.Tensor]) -> None:
            computation(state, x)
            state.set_ready_for_exporting_onnx()

        def forward(self, *x: list[torch.Tensor]) -> tuple[IsResultPrecise, torch.Tensor]:
            # print('x sy: ')
            return computation(state, x)
    # print('state:: ', state.aggregate_witness_path)
    return state, Model

